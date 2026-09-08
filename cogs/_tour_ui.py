"""Primitives d'interaction Discord pour la Tour RPG (cogs/tour.py).

Préfixé par `_` pour que utils/cog_loader.py ne tente pas de le charger
comme une extension à part (même convention que cogs/_xp_common.py).
"""

import asyncio
from typing import Callable

import discord
from discord.ext import commands

CHOICE_TIMEOUT = 30.0


class RunTimeout(Exception):
    pass


class RunEnded(Exception):
    """Levée quand la run du joueur se termine (mort). Propagée jusqu'à
    _play_run, qui l'intercepte pour arrêter proprement la boucle."""
    pass


async def _disable_and_edit(view: discord.ui.View, message: discord.Message | None) -> None:
    for item in view.children:
        item.disabled = True
    if message is not None:
        try:
            await message.edit(view=view)
        except discord.HTTPException:
            pass


class ChoiceButton(discord.ui.Button):
    def __init__(self, value: str, label: str, style: discord.ButtonStyle) -> None:
        super().__init__(label=label, style=style)
        self.value = value

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ChoiceView = self.view
        if interaction.user.id != view.author_id:
            await interaction.response.send_message("❌ Ce choix n'est pas le tien.", ephemeral=True)
            return
        view.value = self.value
        for item in view.children:
            item.disabled = True
        await interaction.response.edit_message(view=view)
        view.stop()


class ChoiceView(discord.ui.View):
    def __init__(
        self, author_id: int, options: list[tuple[str, str, discord.ButtonStyle]], timeout: float
    ) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: str | None = None
        self.message: discord.Message | None = None
        for value, label, style in options:
            self.add_item(ChoiceButton(value, label, style))

    async def on_timeout(self) -> None:
        await _disable_and_edit(self, self.message)


async def _await_view(view: discord.ui.View, message: discord.Message) -> None:
    view.message = message
    timed_out = await view.wait()
    if timed_out:
        raise RunTimeout()


async def ask_choice(
    ctx: commands.Context,
    embed: discord.Embed,
    options: list[tuple[str, str, discord.ButtonStyle]],
    *,
    timeout: float = CHOICE_TIMEOUT,
) -> str:
    """options = [(value, label, style), ...] (max 5). Envoie embed+boutons,
    attend le clic du bon auteur, retourne value. Lève RunTimeout sinon."""
    view = ChoiceView(ctx.author.id, options, timeout)
    message = await ctx.send(embed=embed, view=view)
    await _await_view(view, message)
    return view.value


async def attach_choice(
    message: discord.Message,
    author_id: int,
    options: list[tuple[str, str, discord.ButtonStyle]],
    *,
    embed: discord.Embed | None = None,
    attachments: list[discord.File] | None = None,
    timeout: float = CHOICE_TIMEOUT,
) -> str:
    """Comme ask_choice mais édite un message existant au lieu d'en envoyer
    un nouveau -- utilisé par le HUD de combat de la Tour pour garder un
    seul message persistant édité à chaque round plutôt qu'un par tour."""
    view = ChoiceView(author_id, options, timeout)
    kwargs: dict = {"view": view}
    if embed is not None:
        kwargs["embed"] = embed
    if attachments is not None:
        kwargs["attachments"] = attachments
    await message.edit(**kwargs)
    await _await_view(view, message)
    return view.value


class _ChoiceSelect(discord.ui.Select):
    def __init__(
        self, author_id: int, options: list[tuple[str, str, str | None]], placeholder: str
    ) -> None:
        self.author_id = author_id
        select_options = [
            discord.SelectOption(label=label[:100], value=value, description=(desc or None) and desc[:100])
            for value, label, desc in options
        ]
        super().__init__(placeholder=placeholder, options=select_options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: _SelectView = self.view
        if interaction.user.id != view.author_id:
            await interaction.response.send_message("❌ Ce menu n'est pas le tien.", ephemeral=True)
            return
        view.value = self.values[0]
        for item in view.children:
            item.disabled = True
        await interaction.response.edit_message(view=view)
        view.stop()


class _SelectView(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        options: list[tuple[str, str, str | None]],
        placeholder: str,
        timeout: float,
    ) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: str | None = None
        self.message: discord.Message | None = None
        self.add_item(_ChoiceSelect(author_id, options, placeholder))

    async def on_timeout(self) -> None:
        await _disable_and_edit(self, self.message)


async def ask_select(
    ctx: commands.Context,
    embed: discord.Embed,
    options: list[tuple[str, str, str | None]],
    placeholder: str,
    *,
    timeout: float = CHOICE_TIMEOUT,
) -> str:
    """options = [(value, label, description), ...] (max 25, Discord Select
    limit). Même contrat que ask_choice mais via un menu déroulant."""
    view = _SelectView(ctx.author.id, options, placeholder, timeout)
    message = await ctx.send(embed=embed, view=view)
    view.message = message
    timed_out = await view.wait()
    if timed_out:
        raise RunTimeout()
    return view.value


class _AnswerModal(discord.ui.Modal):
    def __init__(
        self,
        title: str,
        field_label: str,
        validator: Callable[[str], str | None] | None,
        future: asyncio.Future,
    ) -> None:
        super().__init__(title=title)
        self.validator = validator
        self.future = future
        self.answer = discord.ui.TextInput(label=field_label, style=discord.TextStyle.short, max_length=200)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.answer.value
        error = self.validator(value) if self.validator else None
        if error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return
        if not self.future.done():
            self.future.set_result(value)
        await interaction.response.send_message("✅ Réponse envoyée.", ephemeral=True)


class _TriggerButton(discord.ui.Button):
    def __init__(
        self,
        author_id: int,
        label: str,
        modal_title: str,
        field_label: str,
        validator: Callable[[str], str | None] | None,
        future: asyncio.Future,
    ) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.author_id = author_id
        self.modal_title = modal_title
        self.field_label = field_label
        self.validator = validator
        self.future = future

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce bouton n'est pas le tien.", ephemeral=True)
            return
        await interaction.response.send_modal(
            _AnswerModal(self.modal_title, self.field_label, self.validator, self.future)
        )


class _TriggerView(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        label: str,
        modal_title: str,
        field_label: str,
        validator: Callable[[str], str | None] | None,
        future: asyncio.Future,
        timeout: float,
    ) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None
        self.add_item(_TriggerButton(author_id, label, modal_title, field_label, validator, future))

    async def on_timeout(self) -> None:
        await _disable_and_edit(self, self.message)


async def ask_text(
    ctx: commands.Context,
    trigger_label: str,
    modal_title: str,
    field_label: str,
    *,
    embed: discord.Embed | None = None,
    validator: Callable[[str], str | None] | None = None,
    timeout: float = CHOICE_TIMEOUT,
) -> str:
    """Envoie un bouton qui ouvre un Modal (1 champ texte). validator
    retourne un message d'erreur (réaffiché en éphémère, le joueur peut
    recliquer) ou None si la réponse est valide. Lève RunTimeout sinon."""
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    view = _TriggerView(ctx.author.id, trigger_label, modal_title, field_label, validator, future, timeout)
    message = await ctx.send(embed=embed, view=view)
    view.message = message
    try:
        result = await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        await _disable_and_edit(view, message)
        raise RunTimeout()
    await _disable_and_edit(view, message)
    return result
