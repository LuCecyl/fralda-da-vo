# Fralda da Vó

Site: https://lucecyl.github.io/fralda-da-vo/

Todo dia às 7h (Brasília) um robô do GitHub busca o preço da **Bigfral Moviment G/XG**, atualiza o site e manda e-mail se o preço estiver bom.

## Mudar o preço-alvo
Edite `config.json` aqui no GitHub (ícone de lápis) e mude `precoAlvoPorFralda`.

## Atualizar agora
Aba **Actions** → **Atualizar preços** → **Run workflow**.

## Segredos (Settings → Secrets and variables → Actions)
| Nome | Para quê |
|---|---|
| `EMAIL_USUARIO` | Gmail que envia o alerta |
| `EMAIL_SENHA_APP` | Senha de app desse Gmail (myaccount.google.com/apppasswords) |
| `EMAIL_PARA` | Quem recebe, separado por vírgula |
| `ML_CLIENT_ID`, `ML_CLIENT_SECRET` | App do Mercado Livre (developers.mercadolivre.com.br) |
| `SHOPEE_APP_ID`, `SHOPEE_SECRET` | Open API do Shopee Afiliados |

Sem esses segredos o site funciona igual; só não manda e-mail nem lê Mercado Livre/Shopee.
