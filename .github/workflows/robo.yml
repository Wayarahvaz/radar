name: Robo de Vagas

on:
  schedule:
    - cron: "17 10 * * 1-5"   # seg a sex, 10:17 UTC = 7:17 em Brasília
  workflow_dispatch:           # botão pra rodar na hora

permissions:
  contents: write              # deixa o robô salvar o caderno

jobs:
  rodar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install requests

      - name: Buscar vagas e mandar no WhatsApp
        env:
          CALLMEBOT_PHONE: ${{ secrets.CALLMEBOT_PHONE }}
          CALLMEBOT_APIKEY: ${{ secrets.CALLMEBOT_APIKEY }}
        run: python robo.py

      - name: Salvar o caderno
        run: |
          git config user.name "robo-vagas"
          git config user.email "robo-vagas@users.noreply.github.com"
          git add vistas.json
          git diff --staged --quiet || git commit -m "vagas vistas $(date +%F)"
          git push
