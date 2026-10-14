#!/usr/bin/env python3
"""Vigia externo do Painel TV. Roda no GitHub Actions a cada 15 min (fora do servidor e fora do PC).

Lê https://tv.flavio.rio.br/health.php e confere, sem segredos:
  • site no ar (health.php, painel e player respondem);
  • cron do servidor vivo (< 15 min);
  • backup externo recente (< 26 h);
  • disco livre (> 500 MB) e erros na última hora (< 20);
  • TVs: entre 8h e 20h (Brasília) com telas cadastradas e NENHUMA online é problema.

Avisa no Telegram só quando o estado muda (ok → problema, problema → ok), no resumo diário (MODO=resumo)
e, se continuar com problema, a cada 6 h. O estado anterior vem de estado/estado.json (cache do Actions);
a execução sempre termina com sucesso para o GitHub não mandar e-mail de falha a cada checagem.

Variáveis de ambiente: TELEGRAM_TOKEN, TELEGRAM_CHAT, PTV_BASE (padrão https://tv.flavio.rio.br),
MODO (resumo | vazio), ESTADO_DIR (pasta do estado, padrão 'estado').
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019

BASE = os.environ.get('PTV_BASE', 'https://tv.flavio.rio.br').rstrip('/')
UA = {'User-Agent': 'PainelTV-vigia/1.0 (+https://github.com/FLF78/painel-tv-vigia)'}
problemas, info = [], []

def pegar(caminho, timeout=30):
    req = urllib.request.Request(BASE + caminho, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

# 1) health.php
h = None
try:
    st, corpo = pegar('/health.php')
    h = json.loads(corpo)
except urllib.error.HTTPError as e:
    problemas.append(f'health.php respondeu HTTP {e.code}')
except Exception as e:
    problemas.append(f'health.php inacessível: {type(e).__name__}: {e}')

if h:
    mins = lambda s: f'{s // 60} min' if s is not None else 'nunca'
    if not h.get('ok'):
        problemas.append('cron do servidor parado há ' + mins(h.get('cron_idade_s')))
    bk = h.get('backup_externo_idade_s')
    if bk is None or bk > 26 * 3600:
        problemas.append('backup externo atrasado (' + (f'{bk // 3600} h' if bk is not None else 'nunca feito') + ')')
    if h.get('disco_livre_mb') is not None and h['disco_livre_mb'] < 500:
        problemas.append(f"disco livre baixo: {h['disco_livre_mb']} MB")
    if h.get('erros_ultima_hora', 0) >= 20:
        problemas.append(f"{h['erros_ultima_hora']} erros na última hora")
    telas = h.get('telas') or {}
    agora_br = datetime.now(BRASILIA)
    if telas.get('total', 0) > 0 and telas.get('online', 0) == 0 and 8 <= agora_br.hour < 20:
        problemas.append(f"nenhuma das {telas['total']} TVs online às {agora_br:%H:%M} (horário de funcionamento)")
    info.append(f"TVs online {telas.get('online', '?')}/{telas.get('total', '?')} · cron há {mins(h.get('cron_idade_s'))} · "
                f"backup há {bk // 3600 if bk is not None else '?'} h · disco livre {h.get('disco_livre_mb')} MB · erros/h {h.get('erros_ultima_hora')}")

# 2) painel e player no ar
for caminho, nome in (('/', 'painel'), ('/p.php', 'player')):
    try:
        st, corpo = pegar(caminho)
        if st != 200 or len(corpo) < 500:
            problemas.append(f'{nome} respondeu {st} com {len(corpo)} bytes')
    except Exception as e:
        problemas.append(f'{nome} fora do ar: {type(e).__name__}')

ok = not problemas
# Estado entre execuções: arquivo estado/estado.json (o workflow o guarda no cache do Actions). A execução nunca "falha":
# o GitHub não manda e-mail a cada checagem; o aviso é só pelo Telegram.
ARQ_ESTADO = os.path.join(os.environ.get('ESTADO_DIR', 'estado'), 'estado.json')
try:
    anterior_j = json.load(open(ARQ_ESTADO, encoding='utf-8'))
except Exception:
    anterior_j = {}
estado_ant = anterior_j.get('estado', 'desconhecido')
modo = os.environ.get('MODO', '')
agora_ts = int(datetime.now(timezone.utc).timestamp())
ultimo_ok = int(anterior_j.get('ultimo_ok') or 0)
ultimo_lembrete = int(anterior_j.get('ultimo_lembrete') or 0)
horas_desde_ok = (agora_ts - ultimo_ok) / 3600 if ultimo_ok else 0

mudou = (ok and estado_ant == 'problema') or ((not ok) and estado_ant != 'problema')
lembrete = bool((not ok) and estado_ant == 'problema' and agora_ts - (ultimo_lembrete or ultimo_ok or agora_ts) >= 6 * 3600)  # a cada 6 h enquanto persistir
avisar = modo == 'resumo' or mudou or lembrete

cab = ('✅ Painel TV: tudo certo' if ok else '❌ Painel TV: atenção')
if ok and estado_ant == 'problema':
    cab = '✅ Painel TV: normalizado'
if modo == 'resumo':
    cab = ('☀️ Resumo diário · ' + cab)
msg = cab + '\n' + '\n'.join('• ' + x for x in info + problemas) + '\n(vigia externo · GitHub Actions)'
print(msg)
print(f'[estado anterior: {estado_ant} · mudou: {mudou} · modo: {modo or "-"} · avisar: {avisar}]')

os.makedirs(os.path.dirname(ARQ_ESTADO), exist_ok=True)
json.dump({'estado': 'ok' if ok else 'problema', 'ultimo_ok': agora_ts if ok else ultimo_ok, 'ultimo_lembrete': agora_ts if (lembrete or mudou) else ultimo_lembrete,
           'quando': agora_ts, 'resumo': (info + problemas)}, open(ARQ_ESTADO, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

if avisar:
    tok, chat = os.environ.get('TELEGRAM_TOKEN', ''), os.environ.get('TELEGRAM_CHAT', '')
    if tok and chat:
        try:
            dados = json.dumps({'chat_id': chat, 'text': msg, 'disable_web_page_preview': True}).encode()
            urllib.request.urlopen(urllib.request.Request(f'https://api.telegram.org/bot{tok}/sendMessage', data=dados,
                                   headers={'Content-Type': 'application/json'}), timeout=20).read()
            print('[telegram enviado]')
        except Exception as e:
            print('[telegram falhou]', type(e).__name__)
    else:
        print('[telegram não configurado]')
sys.exit(0)  # problema detectado não é falha do vigia; o estado está no arquivo
