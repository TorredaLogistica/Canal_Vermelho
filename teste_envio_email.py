import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo


def validar_variavel(nome):
    valor = os.getenv(nome)

    if not valor:
        raise ValueError(
            f"A variável {nome} não foi configurada nos GitHub Secrets."
        )

    return valor


email_remetente = validar_variavel("EMAIL_REMETENTE")
email_senha = validar_variavel("EMAIL_SENHA")
email_destinatario = validar_variavel("EMAIL_DESTINATARIO")

data_execucao = datetime.now(
    ZoneInfo("America/Sao_Paulo")
).strftime("%d/%m/%Y às %H:%M:%S")

mensagem = EmailMessage()

mensagem["From"] = email_remetente
mensagem["To"] = email_destinatario
mensagem["Subject"] = "Teste automático - Canal Vermelho"

mensagem.set_content(
    f"""
Olá,

Este é um teste de envio automático executado pelo GitHub Actions.

Repositório: Canal_Vermelho
Data da execução: {data_execucao}

Nenhuma informação da Base OTIF foi enviada neste teste.

Atenciosamente,
Torre de Logística
""".strip()
)

with smtplib.SMTP("smtp.office365.com", 587, timeout=60) as servidor:
    servidor.ehlo()
    servidor.starttls()
    servidor.ehlo()
    servidor.login(email_remetente, email_senha)
    servidor.send_message(mensagem)

print("E-mail de teste enviado com sucesso.")
print(f"Data da execução: {data_execucao}")
