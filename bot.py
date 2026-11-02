#!/usr/bin/env python3
"""
VIPBot — Bot de divulgação para grupos/canais Telegram
Instalação: pip install python-telegram-bot aiohttp aiofiles
Uso: python bot.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from aiohttp import web
from telegram import (
    Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMemberUpdated,
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    ChatMemberHandler, MessageHandler, CallbackQueryHandler, filters,
)
from telegram.error import TelegramError

# ══════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════

BASE      = Path(__file__).parent
DATA_FILE = BASE / "data.json"
LOG_FILE  = BASE / "vipbot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════
# DADOS PERSISTENTES
# ══════════════════════════════════════════

DEFAULT_DATA = {
    "token": "",
    "welcome": {
        "enabled": True,
        "text": "👋 Bem-vindo(a), {nome}! 🔥\n\nVocê entrou no melhor VIP do Telegram.\nAproveite o conteúdo exclusivo! 😈",
        "media_type": "none",   # none | photo | video
        "file_id": "",
        "buttons": [],
    },
    "broadcast": {
        "text": "🔥 *CONTEÚDO EXCLUSIVO* 🔥\n\nClique abaixo e acesse agora!",
        "media_type": "none",
        "file_id": "",
        "buttons": [],
    },
    "auto_broadcast": {
        "enabled": False,
        "interval_hours": 1,
        "last_sent": None,
    },
    "stats": {
        "groups": {},          # chat_id → {"title", "joined_at", "members_welcomed"}
        "total_welcomed": 0,
        "total_broadcasts": 0,
        "broadcast_log": [],   # últimos 50
    },
}


def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_DATA))


def save_data(d: dict):
    DATA_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════

def make_keyboard(buttons: list) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows = []
    for b in buttons:
        if b.get("title") and b.get("url"):
            rows.append([InlineKeyboardButton(b["title"], url=b["url"])])
    return InlineKeyboardMarkup(rows) if rows else None


async def send_message(bot: Bot, chat_id, text: str, media_type: str,
                       file_id: str, buttons: list):
    kb = make_keyboard(buttons)
    try:
        if media_type == "photo" and file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=text, parse_mode="Markdown",
                                 reply_markup=kb)
        elif media_type == "video" and file_id:
            await bot.send_video(chat_id=chat_id, video=file_id,
                                 caption=text, parse_mode="Markdown",
                                 reply_markup=kb)
        else:
            await bot.send_message(chat_id=chat_id, text=text,
                                   parse_mode="Markdown", reply_markup=kb)
        return True
    except TelegramError as e:
        log.warning(f"Erro ao enviar para {chat_id}: {e}")
        return False


# ══════════════════════════════════════════
# MENUS INLINE
# ══════════════════════════════════════════

def menu_principal():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Estatísticas",       callback_data="menu_stats")],
        [InlineKeyboardButton("👋 Boas-vindas",        callback_data="menu_welcome"),
         InlineKeyboardButton("📣 Mensagem",           callback_data="menu_broadcast")],
        [InlineKeyboardButton("🚀 Disparar agora",     callback_data="menu_dispatch")],
        [InlineKeyboardButton("⏱ Automático",          callback_data="menu_auto"),
         InlineKeyboardButton("⚙️ Configuração",       callback_data="menu_config")],
    ])


async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    d  = load_data()
    ab = d["auto_broadcast"]
    wc = d["welcome"]
    grupos = len(d["stats"]["groups"])
    auto_txt = f"✅ {ab['interval_hours']}h" if ab["enabled"] else "❌ Off"
    bv_txt   = "✅ On" if wc["enabled"] else "❌ Off"

    texto = (
        "🤖 *VIPBot — Painel de Controle*\n\n"
        f"👥 Grupos ativos: *{grupos}*\n"
        f"👋 Boas-vindas: *{bv_txt}*\n"
        f"⏱ Auto-disparo: *{auto_txt}*\n\n"
        "Escolha uma opção abaixo:"
    )
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(texto, parse_mode="Markdown", reply_markup=menu_principal())
    else:
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg:
            await msg.reply_text(texto, parse_mode="Markdown", reply_markup=menu_principal())


# ══════════════════════════════════════════
# HANDLERS TELEGRAM
# ══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mostrar_menu(update, context)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mostrar_menu(update, context)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    await q.answer()

    d  = load_data()
    ab = d["auto_broadcast"]
    wc = d["welcome"]
    bc = d["broadcast"]

    # ── STATS ──
    if data == "menu_stats":
        grupos = d["stats"]["groups"]
        total_g = len(grupos)
        total_w = d["stats"]["total_welcomed"]
        total_b = d["stats"]["total_broadcasts"]
        auto_s  = f"✅ A cada {ab['interval_hours']}h" if ab["enabled"] else "❌ Desativado"
        lista = ""
        for gid, g in list(grupos.items())[:10]:
            lista += f"\n• {g.get('title', gid)} — 👋 {g.get('members_welcomed',0)}"
        if not lista:
            lista = "\nNenhum grupo ainda."
        txt = (
            f"📊 *Estatísticas*\n\n"
            f"👥 Grupos/canais: *{total_g}*\n"
            f"👋 Boas-vindas enviadas: *{total_w}*\n"
            f"📣 Disparos feitos: *{total_b}*\n"
            f"⏱ Automático: {auto_s}\n\n"
            f"*Grupos ativos:*{lista}"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_inicio")]])
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)

    # ── BOAS-VINDAS ──
    elif data == "menu_welcome":
        status = "✅ Ativadas" if wc["enabled"] else "❌ Desativadas"
        midia  = wc.get("media_type","none")
        btns_n = len(wc.get("buttons",[]))
        txt = (
            f"👋 *Boas-vindas*\n\n"
            f"Status: {status}\n"
            f"Mídia: {midia}\n"
            f"Botões: {btns_n}\n\n"
            f"*Texto atual:*\n{wc.get('text','')[:300]}"
        )
        toggle_lbl = "🔴 Desativar" if wc["enabled"] else "🟢 Ativar"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(toggle_lbl, callback_data="wc_toggle")],
            [InlineKeyboardButton("✏️ Editar texto", callback_data="wc_edit_text")],
            [InlineKeyboardButton("🖼 Definir mídia", callback_data="wc_edit_media")],
            [InlineKeyboardButton("🔘 Gerenciar botões", callback_data="wc_buttons")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_inicio")],
        ])
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)

    elif data == "wc_toggle":
        d["welcome"]["enabled"] = not wc["enabled"]
        save_data(d)
        await callback_handler(update, context)  # re-render

    elif data == "wc_edit_text":
        context.user_data["esperando"] = "wc_text"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu_welcome")]])
        await q.edit_message_text(
            "✏️ *Editar texto das boas-vindas*\n\n"
            "Use `{nome}` para o nome do membro.\n\n"
            "Envie o novo texto agora:",
            parse_mode="Markdown", reply_markup=kb
        )

    elif data == "wc_edit_media":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Sem mídia",  callback_data="wc_media_none")],
            [InlineKeyboardButton("📷 Foto",       callback_data="wc_media_photo")],
            [InlineKeyboardButton("🎥 Vídeo",      callback_data="wc_media_video")],
            [InlineKeyboardButton("⬅️ Voltar",     callback_data="menu_welcome")],
        ])
        await q.edit_message_text("🖼 *Tipo de mídia nas boas-vindas:*", parse_mode="Markdown", reply_markup=kb)

    elif data in ("wc_media_none","wc_media_photo","wc_media_video"):
        tipo = data.replace("wc_media_","")
        d["welcome"]["media_type"] = tipo
        save_data(d)
        if tipo != "none":
            context.user_data["esperando"] = "wc_fileid"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu_welcome")]])
            await q.edit_message_text(
                f"{'📷' if tipo=='photo' else '🎥'} Envie a *{'foto' if tipo=='photo' else 'vídeo'}* agora para obter o File ID automaticamente,\nou envie o File ID diretamente como texto:",
                parse_mode="Markdown", reply_markup=kb
            )
        else:
            d["welcome"]["file_id"] = ""
            save_data(d)
            await mostrar_menu(update, context, edit=True)

    elif data == "wc_buttons":
        btns = wc.get("buttons", [])
        lista = "\n".join([f"{i+1}. {b['title']} → {b['url']}" for i,b in enumerate(btns)]) or "Nenhum botão ainda."
        kb_rows = [[InlineKeyboardButton(f"❌ Remover botão {i+1}", callback_data=f"wc_rm_btn_{i}")] for i in range(len(btns))]
        kb_rows.append([InlineKeyboardButton("➕ Adicionar botão", callback_data="wc_add_btn")])
        kb_rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_welcome")])
        await q.edit_message_text(f"🔘 *Botões das boas-vindas:*\n\n{lista}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_rows))

    elif data == "wc_add_btn":
        context.user_data["esperando"] = "wc_btn_title"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="wc_buttons")]])
        await q.edit_message_text("🔘 Digite o *título* do botão:", parse_mode="Markdown", reply_markup=kb)

    elif data.startswith("wc_rm_btn_"):
        idx = int(data.split("_")[-1])
        btns = d["welcome"].get("buttons", [])
        if 0 <= idx < len(btns):
            btns.pop(idx)
            d["welcome"]["buttons"] = btns
            save_data(d)
        # re-render
        q.data = "wc_buttons"
        await callback_handler(update, context)

    # ── BROADCAST ──
    elif data == "menu_broadcast":
        midia  = bc.get("media_type","none")
        btns_n = len(bc.get("buttons",[]))
        txt = (
            f"📣 *Mensagem de disparo*\n\n"
            f"Mídia: {midia}\n"
            f"Botões: {btns_n}\n\n"
            f"*Texto atual:*\n{bc.get('text','')[:300]}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Editar texto",    callback_data="bc_edit_text")],
            [InlineKeyboardButton("🖼 Definir mídia",   callback_data="bc_edit_media")],
            [InlineKeyboardButton("🔘 Gerenciar botões",callback_data="bc_buttons")],
            [InlineKeyboardButton("⬅️ Voltar",          callback_data="menu_inicio")],
        ])
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)

    elif data == "bc_edit_text":
        context.user_data["esperando"] = "bc_text"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu_broadcast")]])
        await q.edit_message_text(
            "✏️ *Editar texto do disparo*\n\nSuporta *negrito*, _itálico_, [link](url)\n\nEnvie o novo texto:",
            parse_mode="Markdown", reply_markup=kb
        )

    elif data == "bc_edit_media":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Sem mídia",  callback_data="bc_media_none")],
            [InlineKeyboardButton("📷 Foto",       callback_data="bc_media_photo")],
            [InlineKeyboardButton("🎥 Vídeo",      callback_data="bc_media_video")],
            [InlineKeyboardButton("⬅️ Voltar",     callback_data="menu_broadcast")],
        ])
        await q.edit_message_text("🖼 *Tipo de mídia no disparo:*", parse_mode="Markdown", reply_markup=kb)

    elif data in ("bc_media_none","bc_media_photo","bc_media_video"):
        tipo = data.replace("bc_media_","")
        d["broadcast"]["media_type"] = tipo
        save_data(d)
        if tipo != "none":
            context.user_data["esperando"] = "bc_fileid"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu_broadcast")]])
            await q.edit_message_text(
                f"{'📷' if tipo=='photo' else '🎥'} Envie a mídia agora ou cole o File ID como texto:",
                parse_mode="Markdown", reply_markup=kb
            )
        else:
            d["broadcast"]["file_id"] = ""
            save_data(d)
            await mostrar_menu(update, context, edit=True)

    elif data == "bc_buttons":
        btns = bc.get("buttons", [])
        lista = "\n".join([f"{i+1}. {b['title']} → {b['url']}" for i,b in enumerate(btns)]) or "Nenhum botão ainda."
        kb_rows = [[InlineKeyboardButton(f"❌ Remover botão {i+1}", callback_data=f"bc_rm_btn_{i}")] for i in range(len(btns))]
        kb_rows.append([InlineKeyboardButton("➕ Adicionar botão", callback_data="bc_add_btn")])
        kb_rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_broadcast")])
        await q.edit_message_text(f"🔘 *Botões do disparo:*\n\n{lista}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_rows))

    elif data == "bc_add_btn":
        context.user_data["esperando"] = "bc_btn_title"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="bc_buttons")]])
        await q.edit_message_text("🔘 Digite o *título* do botão:", parse_mode="Markdown", reply_markup=kb)

    elif data.startswith("bc_rm_btn_"):
        idx = int(data.split("_")[-1])
        btns = d["broadcast"].get("buttons", [])
        if 0 <= idx < len(btns):
            btns.pop(idx)
            d["broadcast"]["buttons"] = btns
            save_data(d)
        q.data = "bc_buttons"
        await callback_handler(update, context)

    # ── DISPATCH ──
    elif data == "menu_dispatch":
        grupos = list(d["stats"]["groups"].keys())
        n = len(grupos)
        txt = (
            f"🚀 *Disparar agora*\n\n"
            f"Grupos/canais ativos: *{n}*\n\n"
            f"Isso enviará a mensagem configurada para todos os {n} grupo(s) agora.\n\n"
            f"Confirmar?"
        )
        if n == 0:
            txt = "🚀 *Disparar agora*\n\n❌ Nenhum grupo ativo ainda.\nAdicione o bot como admin em um grupo primeiro."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_inicio")]])
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirmar disparo", callback_data="dispatch_confirm")],
                [InlineKeyboardButton("⬅️ Cancelar",         callback_data="menu_inicio")],
            ])
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)

    elif data == "dispatch_confirm":
        await q.edit_message_text("📣 Disparando... aguarde.")
        bc     = d["broadcast"]
        grupos = list(d["stats"]["groups"].keys())
        bot    = context.bot
        ok = err = 0
        for gid in grupos:
            success = await send_message(bot, int(gid), bc["text"], bc["media_type"], bc["file_id"], bc["buttons"])
            if success: ok += 1
            else: err += 1
            await asyncio.sleep(0.4)
        d["stats"]["total_broadcasts"] += 1
        d["stats"]["broadcast_log"].append({"at": datetime.now().isoformat(), "type": "telegram", "ok": ok, "err": err})
        d["stats"]["broadcast_log"] = d["stats"]["broadcast_log"][-50:]
        save_data(d)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data="menu_inicio")]])
        await q.edit_message_text(f"✅ *Disparo concluído!*\n\n✓ {ok} enviados\n✗ {err} falhas", parse_mode="Markdown", reply_markup=kb)

    # ── AUTO ──
    elif data == "menu_auto":
        status = "✅ Ativado" if ab["enabled"] else "❌ Desativado"
        last   = ab.get("last_sent","")
        prox   = "—"
        if ab["enabled"] and last:
            from datetime import datetime, timedelta
            d2 = datetime.fromisoformat(last) + timedelta(hours=int(ab["interval_hours"]))
            prox = d2.strftime("%d/%m %H:%M")
        toggle_lbl = "🔴 Desativar" if ab["enabled"] else "🟢 Ativar"
        txt = (
            f"⏱ *Disparo automático*\n\n"
            f"Status: {status}\n"
            f"Intervalo: {ab['interval_hours']}h\n"
            f"Próximo: {prox}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(toggle_lbl,         callback_data="auto_toggle")],
            [InlineKeyboardButton("🕐 1h",  callback_data="auto_int_1"),
             InlineKeyboardButton("🕒 3h",  callback_data="auto_int_3"),
             InlineKeyboardButton("🕕 6h",  callback_data="auto_int_6")],
            [InlineKeyboardButton("🕛 12h", callback_data="auto_int_12"),
             InlineKeyboardButton("🗓 24h", callback_data="auto_int_24")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_inicio")],
        ])
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)

    elif data == "auto_toggle":
        d["auto_broadcast"]["enabled"] = not ab["enabled"]
        save_data(d)
        q.data = "menu_auto"
        await callback_handler(update, context)

    elif data.startswith("auto_int_"):
        h = int(data.split("_")[-1])
        d["auto_broadcast"]["interval_hours"] = h
        save_data(d)
        q.data = "menu_auto"
        await callback_handler(update, context)

    # ── CONFIG ──
    elif data == "menu_config":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Alterar token",   callback_data="cfg_token")],
            [InlineKeyboardButton("⬅️ Voltar",          callback_data="menu_inicio")],
        ])
        await q.edit_message_text(
            "⚙️ *Configuração*\n\n"
            "O token já está configurado.\n"
            "Use o painel web para configurações avançadas.",
            parse_mode="Markdown", reply_markup=kb
        )

    elif data == "cfg_token":
        context.user_data["esperando"] = "cfg_token"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="menu_config")]])
        await q.edit_message_text("🔑 Envie o novo token do @BotFather:", parse_mode="Markdown", reply_markup=kb)

    # ── VOLTAR ──
    elif data == "menu_inicio":
        await mostrar_menu(update, context, edit=True)


async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe textos digitados pelo usuário para configurar o bot."""
    esperando = context.user_data.get("esperando")
    msg  = update.message
    text = msg.text.strip() if msg.text else ""

    if not esperando:
        # Se mandou mídia sem estar esperando, captura file_id
        await capturar_fileid(update, context)
        return

    d = load_data()

    # ── Textos ──
    if esperando == "wc_text":
        d["welcome"]["text"] = text
        save_data(d)
        context.user_data.pop("esperando", None)
        await msg.reply_text("✅ Texto das boas-vindas atualizado!", reply_markup=menu_principal())

    elif esperando == "bc_text":
        d["broadcast"]["text"] = text
        save_data(d)
        context.user_data.pop("esperando", None)
        await msg.reply_text("✅ Texto do disparo atualizado!", reply_markup=menu_principal())

    # ── File IDs ──
    elif esperando == "wc_fileid":
        if msg.photo:
            fid = msg.photo[-1].file_id
        elif msg.video:
            fid = msg.video.file_id
        else:
            fid = text
        d["welcome"]["file_id"] = fid
        save_data(d)
        context.user_data.pop("esperando", None)
        await msg.reply_text(f"✅ Mídia das boas-vindas salva!\n`{fid}`", parse_mode="Markdown", reply_markup=menu_principal())

    elif esperando == "bc_fileid":
        if msg.photo:
            fid = msg.photo[-1].file_id
        elif msg.video:
            fid = msg.video.file_id
        else:
            fid = text
        d["broadcast"]["file_id"] = fid
        save_data(d)
        context.user_data.pop("esperando", None)
        await msg.reply_text(f"✅ Mídia do disparo salva!\n`{fid}`", parse_mode="Markdown", reply_markup=menu_principal())

    # ── Botões ──
    elif esperando == "wc_btn_title":
        context.user_data["btn_title_tmp"] = text
        context.user_data["esperando"] = "wc_btn_url"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="wc_buttons")]])
        await msg.reply_text(f"🔗 Agora envie a URL do botão *\"{text}\"*:", parse_mode="Markdown", reply_markup=kb)

    elif esperando == "wc_btn_url":
        title = context.user_data.pop("btn_title_tmp", "Botão")
        if not text.startswith("http"):
            await msg.reply_text("❌ URL inválida. Deve começar com http:// ou https://")
            return
        d["welcome"].setdefault("buttons", []).append({"title": title, "url": text})
        save_data(d)
        context.user_data.pop("esperando", None)
        await msg.reply_text(f"✅ Botão *\"{title}\"* adicionado!", parse_mode="Markdown", reply_markup=menu_principal())

    elif esperando == "bc_btn_title":
        context.user_data["btn_title_tmp"] = text
        context.user_data["esperando"] = "bc_btn_url"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="bc_buttons")]])
        await msg.reply_text(f"🔗 Agora envie a URL do botão *\"{text}\"*:", parse_mode="Markdown", reply_markup=kb)

    elif esperando == "bc_btn_url":
        title = context.user_data.pop("btn_title_tmp", "Botão")
        if not text.startswith("http"):
            await msg.reply_text("❌ URL inválida. Deve começar com http:// ou https://")
            return
        d["broadcast"].setdefault("buttons", []).append({"title": title, "url": text})
        save_data(d)
        context.user_data.pop("esperando", None)
        await msg.reply_text(f"✅ Botão *\"{title}\"* adicionado!", parse_mode="Markdown", reply_markup=menu_principal())

    # ── Token ──
    elif esperando == "cfg_token":
        d["token"] = text
        save_data(d)
        context.user_data.pop("esperando", None)
        await msg.reply_text("✅ Token salvo! Reinicie o bot para aplicar.", reply_markup=menu_principal())


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = load_data()
    grupos = d["stats"]["groups"]
    total_g = len(grupos)
    total_w = d["stats"]["total_welcomed"]
    total_b = d["stats"]["total_broadcasts"]
    auto    = d["auto_broadcast"]
    status_auto = (
        f"✅ A cada {auto['interval_hours']}h"
        if auto["enabled"] else "❌ Desativado"
    )
    await update.message.reply_text(
        f"📊 *Estatísticas VIPBot*\n\n"
        f"👥 Grupos/canais: *{total_g}*\n"
        f"👋 Boas-vindas enviadas: *{total_w}*\n"
        f"📣 Disparos feitos: *{total_b}*\n"
        f"⏱ Disparo automático: {status_auto}",
        parse_mode="Markdown",
    )


async def cmd_disparar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📣 Iniciando disparo manual...")
    d     = load_data()
    bot   = context.bot
    bc    = d["broadcast"]
    grupos = list(d["stats"]["groups"].keys())
    ok = err = 0
    for gid in grupos:
        success = await send_message(
            bot, int(gid), bc["text"], bc["media_type"],
            bc["file_id"], bc["buttons"],
        )
        if success:
            ok += 1
        else:
            err += 1
        await asyncio.sleep(0.5)
    d["stats"]["total_broadcasts"] += 1
    d["stats"]["broadcast_log"].append({
        "at": datetime.now().isoformat(),
        "type": "manual",
        "ok": ok, "err": err,
    })
    d["stats"]["broadcast_log"] = d["stats"]["broadcast_log"][-50:]
    save_data(d)
    await update.message.reply_text(
        f"✅ Disparo concluído\n✓ {ok} enviados  ✗ {err} falhas"
    )


async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta entrada de novo membro e envia boas-vindas."""
    result: ChatMemberUpdated = update.chat_member
    if result is None:
        return

    old = result.old_chat_member.status
    new = result.new_chat_member.status
    entrou = old in ("left", "kicked") and new in ("member", "administrator", "creator")
    if not entrou:
        return

    d    = load_data()
    chat = result.chat

    # Registra grupo se novo
    gid = str(chat.id)
    if gid not in d["stats"]["groups"]:
        d["stats"]["groups"][gid] = {
            "title": chat.title or chat.username or gid,
            "joined_at": datetime.now().isoformat(),
            "members_welcomed": 0,
        }

    # Boas-vindas
    wc = d["welcome"]
    if wc["enabled"]:
        nome = result.new_chat_member.user.first_name or "membro"
        texto = wc["text"].replace("{nome}", nome)
        success = await send_message(
            context.bot, chat.id, texto,
            wc["media_type"], wc["file_id"], wc["buttons"],
        )
        if success:
            d["stats"]["groups"][gid]["members_welcomed"] = (
                d["stats"]["groups"][gid].get("members_welcomed", 0) + 1
            )
            d["stats"]["total_welcomed"] += 1

    save_data(d)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta quando o bot entra ou sai de um grupo."""
    result: ChatMemberUpdated = update.my_chat_member
    if result is None:
        return

    d    = load_data()
    chat = result.chat
    gid  = str(chat.id)
    new  = result.new_chat_member.status

    if new in ("member", "administrator"):
        if gid not in d["stats"]["groups"]:
            d["stats"]["groups"][gid] = {
                "title": chat.title or chat.username or gid,
                "joined_at": datetime.now().isoformat(),
                "members_welcomed": 0,
            }
            log.info(f"Bot adicionado ao grupo: {chat.title} ({gid})")
    elif new in ("left", "kicked"):
        d["stats"]["groups"].pop(gid, None)
        log.info(f"Bot removido do grupo: {chat.title} ({gid})")

    save_data(d)


async def capturar_fileid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Printa file_id de fotos/vídeos enviados pro bot (DM)."""
    msg = update.message
    if not msg:
        return
    if msg.photo:
        fid = msg.photo[-1].file_id
        log.info(f"[FILE_ID FOTO] {fid}")
        await msg.reply_text(f"📷 *File ID da foto:*\n`{fid}`", parse_mode="Markdown")
    elif msg.video:
        fid = msg.video.file_id
        log.info(f"[FILE_ID VIDEO] {fid}")
        await msg.reply_text(f"🎥 *File ID do vídeo:*\n`{fid}`", parse_mode="Markdown")


# ══════════════════════════════════════════
# DISPARO AUTOMÁTICO
# ══════════════════════════════════════════

async def auto_broadcast_job(context: ContextTypes.DEFAULT_TYPE):
    d  = load_data()
    ab = d["auto_broadcast"]
    if not ab["enabled"]:
        return

    last = ab.get("last_sent")
    interval = timedelta(hours=int(ab["interval_hours"]))
    if last:
        elapsed = datetime.now() - datetime.fromisoformat(last)
        if elapsed < interval:
            return

    bc     = d["broadcast"]
    grupos = list(d["stats"]["groups"].keys())
    if not grupos:
        return

    log.info(f"Auto-disparo para {len(grupos)} grupo(s)...")
    ok = err = 0
    for gid in grupos:
        success = await send_message(
            context.bot, int(gid), bc["text"],
            bc["media_type"], bc["file_id"], bc["buttons"],
        )
        if success:
            ok += 1
        else:
            err += 1
        await asyncio.sleep(0.5)

    d["stats"]["total_broadcasts"] += 1
    d["stats"]["broadcast_log"].append({
        "at": datetime.now().isoformat(),
        "type": "auto",
        "ok": ok, "err": err,
    })
    d["stats"]["broadcast_log"] = d["stats"]["broadcast_log"][-50:]
    d["auto_broadcast"]["last_sent"] = datetime.now().isoformat()
    save_data(d)
    log.info(f"Auto-disparo concluído: {ok} ok / {err} falha")


# ══════════════════════════════════════════
# PAINEL WEB (API REST)
# ══════════════════════════════════════════

async def api_get(request: web.Request) -> web.Response:
    d = load_data()
    # não retorna token completo por segurança
    safe = json.loads(json.dumps(d))
    t = safe.get("token", "")
    safe["token"] = (t[:6] + "..." + t[-4:]) if len(t) > 10 else ("***" if t else "")
    return web.json_response(safe)


async def api_save(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON inválido"}, status=400)

    d = load_data()

    # Token só atualiza se vier não-mascarado
    if "token" in body and "..." not in str(body["token"]) and body["token"]:
        d["token"] = body["token"]

    for key in ("welcome", "broadcast", "auto_broadcast"):
        if key in body:
            d[key].update(body[key])

    save_data(d)
    return web.json_response({"ok": True})


async def api_stats(request: web.Request) -> web.Response:
    d = load_data()
    return web.json_response(d["stats"])


async def api_dispatch(request: web.Request) -> web.Response:
    """Disparo manual via painel."""
    d      = load_data()
    token  = d.get("token", "")
    if not token:
        return web.json_response({"ok": False, "error": "Token não configurado"}, status=400)

    bc     = d["broadcast"]
    grupos = list(d["stats"]["groups"].keys())
    if not grupos:
        return web.json_response({"ok": False, "error": "Nenhum grupo cadastrado"})

    bot = Bot(token=token)
    ok = err = 0
    for gid in grupos:
        success = await send_message(
            bot, int(gid), bc["text"],
            bc["media_type"], bc["file_id"], bc["buttons"],
        )
        if success:
            ok += 1
        else:
            err += 1
        await asyncio.sleep(0.3)

    d["stats"]["total_broadcasts"] += 1
    d["stats"]["broadcast_log"].append({
        "at": datetime.now().isoformat(),
        "type": "painel",
        "ok": ok, "err": err,
    })
    d["stats"]["broadcast_log"] = d["stats"]["broadcast_log"][-50:]
    save_data(d)
    return web.json_response({"ok": True, "sent": ok, "failed": err})


async def api_remove_group(request: web.Request) -> web.Response:
    gid = request.match_info.get("gid")
    d = load_data()
    d["stats"]["groups"].pop(gid, None)
    save_data(d)
    return web.json_response({"ok": True})


def build_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get ("/api/data",         api_get)
    app.router.add_post("/api/save",         api_save)
    app.router.add_get ("/api/stats",        api_stats)
    app.router.add_post("/api/dispatch",     api_dispatch)
    app.router.add_delete("/api/group/{gid}", api_remove_group)
    # Serve o painel HTML
    panel = BASE / "panel.html"
    if panel.exists():
        app.router.add_get("/", lambda r: web.FileResponse(panel))
    return app


# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════

async def main():
    d = load_data()
    token = d.get("token", "").strip()

    if not token:
        log.error(
            "Token não configurado!\n"
            "  1. Abra data.json e preencha o campo 'token'\n"
            "  2. OU acesse http://localhost:8080 após iniciar\n"
            "  Após configurar, reinicie o bot."
        )
        # Inicia só o painel pra facilitar configuração
        web_app = build_web_app()
        runner  = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8081)
        await site.start()
        log.info("Painel disponível em http://localhost:8081")
        await asyncio.sleep(999999)
        return

    # Telegram bot
    tg_app = (
        Application.builder()
        .token(token)
        .build()
    )

    tg_app.add_handler(CommandHandler("start",    cmd_start))
    tg_app.add_handler(CommandHandler("menu",     cmd_menu))
    tg_app.add_handler(CommandHandler("status",   cmd_status))
    tg_app.add_handler(CommandHandler("disparar", cmd_disparar))
    tg_app.add_handler(CallbackQueryHandler(callback_handler))
    tg_app.add_handler(ChatMemberHandler(on_chat_member,    ChatMemberHandler.CHAT_MEMBER))
    tg_app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    tg_app.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO,
        text_input_handler
    ))

    # Job de auto-disparo (verifica a cada 5 min)
    tg_app.job_queue.run_repeating(auto_broadcast_job, interval=300, first=60)

    # Web API
    web_app = build_web_app()
    runner  = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8081)
    await site.start()
    log.info("Painel disponível em http://localhost:8081")

    # Inicia polling
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("VIPBot rodando! Pressione Ctrl+C para parar.")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
