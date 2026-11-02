══════════════════════════════════════════════
  VIPBot — Guia de instalação e uso
══════════════════════════════════════════════

ARQUIVOS:
  bot.py           → código principal do bot
  panel.html       → painel web de configuração
  data.json        → dados e configurações (gerado automaticamente)
  requirements.txt → dependências Python
  README.txt       → este arquivo

──────────────────────────────────────────────
 1. INSTALAÇÃO NO SEU PC (para testar)
──────────────────────────────────────────────

1. Instale Python 3.10+: python.org/downloads
2. Abra o terminal na pasta do bot
3. Execute:
     pip install -r requirements.txt
4. Rode:
     python bot.py
5. Acesse o painel em: http://localhost:8080
6. Cole o token do @BotFather na aba Configuração

──────────────────────────────────────────────
 2. HOSPEDAR GRÁTIS NO RAILWAY (recomendado)
──────────────────────────────────────────────

1. Crie conta em: railway.app (grátis)
2. Crie um novo projeto → "Empty Project"
3. Clique em "+ New" → "GitHub Repo"
   OU arraste os arquivos pelo terminal com:
     npm install -g @railway/cli
     railway login
     railway init
     railway up
4. Vá em Settings → Add Service → Add Variable:
   Nenhuma variável necessária (token fica no data.json)
5. Em "Start Command" coloque:
     python bot.py
6. O bot fica online 24h automaticamente

Painel web ficará disponível na URL pública do Railway.

──────────────────────────────────────────────
 3. HOSPEDAR GRÁTIS NO RENDER.COM (alternativa)
──────────────────────────────────────────────

1. Crie conta em: render.com
2. New → Web Service → conecte o GitHub
3. Build Command:  pip install -r requirements.txt
4. Start Command:  python bot.py
5. Plano: Free

──────────────────────────────────────────────
 4. CONFIGURAÇÕES ESSENCIAIS
──────────────────────────────────────────────

OBTER TOKEN:
  1. Abra o Telegram → @BotFather
  2. Envie /newbot → siga as instruções
  3. Copie o token gerado
  4. Cole no painel → aba Configuração → Salvar

ADICIONAR AO GRUPO/CANAL:
  1. Abra o grupo no Telegram
  2. Adicionar membros → procure seu @seubot
  3. Dê permissão de ADMINISTRADOR (obrigatório para boas-vindas)

OBTER FILE ID DE FOTO/VÍDEO:
  1. Abra o chat privado com seu bot
  2. Envie a foto ou vídeo diretamente
  3. O bot responde com o File ID automaticamente
  4. Copie e cole nos campos de mídia do painel

──────────────────────────────────────────────
 5. FUNCIONALIDADES
──────────────────────────────────────────────

✅ Boas-vindas automáticas com {nome} do membro
✅ Mídia (foto/vídeo) nas boas-vindas e disparos
✅ Botões clicáveis com título e link
✅ Painel web completo em tempo real
✅ Estatísticas de grupos, boas-vindas e disparos
✅ Disparo manual via painel ou comando /disparar
✅ Disparo automático configurável (1h, 2h, 6h, 12h, 24h)
✅ Histórico dos últimos 50 disparos
✅ Lista de todos os grupos com o bot
✅ Remoção de grupos pela lista
✅ Detecção automática de entrada/saída do bot em grupos
✅ Captura automática de File ID ao enviar mídia

COMANDOS DO BOT:
  /start    → mensagem de boas-vindas
  /status   → estatísticas rápidas
  /disparar → disparo manual via Telegram

══════════════════════════════════════════════
