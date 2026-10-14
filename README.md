# Vigia do Painel TV

Monitor externo do [Painel TV](https://tv.flavio.rio.br) (sinalização digital da Tarde com Maria TV).
Roda no GitHub Actions a cada 15 minutos, independente do servidor e de qualquer PC ligado.

O que confere (só dados públicos de `health.php`, sem segredos):

- site no ar: painel, player e `health.php` respondendo;
- cron do servidor vivo (menos de 15 min);
- backup externo recente (menos de 26 h);
- disco livre acima de 500 MB e menos de 20 erros na última hora;
- TVs: entre 8h e 20h (Brasília), telas cadastradas e nenhuma online.

Avisos no Telegram (segredos `TELEGRAM_TOKEN` e `TELEGRAM_CHAT` do repositório):

- quando o estado muda (ok → problema, problema → normalizado);
- resumo diário às 07:00 de Brasília;
- lembrete a cada 6 h enquanto o problema persistir.

Este repositório é público só por causa dos minutos ilimitados do Actions; o código do Painel TV fica em repositório privado.
