"""The emails of the auth domain, as ``Mail`` objects ready for ``core.mailer``.

Text is in Spanish, like the backoffice. Every message has a plain-text part
(the one that always renders) and an HTML one; whatever comes from the user is
escaped before it reaches the HTML.
"""

from __future__ import annotations

from html import escape

from core.mailer import Mail


def _html(name: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    body = "".join(f'<p style="margin:0 0 16px">{p}</p>' for p in paragraphs)
    if button:
        label, url = button
        body += (
            f'<p style="margin:24px 0"><a href="{escape(url, quote=True)}" '
            'style="background:#22d3ee;color:#020617;padding:10px 20px;border-radius:999px;'
            f'text-decoration:none;font-weight:600">{escape(label)}</a></p>'
            '<p style="margin:0 0 16px;font-size:13px;color:#64748b">Si el botón no funciona, copia este enlace '
            f'en tu navegador:<br>{escape(url)}</p>'
        )
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#0f172a;'
        'max-width:520px;margin:0 auto;padding:24px">'
        '<p style="font-size:20px;font-weight:900;margin:0 0 24px">nexova<span style="color:#22d3ee">.</span></p>'
        f'<p style="margin:0 0 16px">Hola, {escape(name)}:</p>{body}'
        '<p style="margin:24px 0 0;font-size:13px;color:#64748b">Nexova Backoffice</p></div>'
    )


def password_reset(to: str, name: str, link: str, minutes: int) -> Mail:
    text = (
        f"Hola, {name}:\n\n"
        "Hemos recibido una solicitud para restablecer la contraseña de tu cuenta de Nexova.\n"
        f"Abre este enlace para elegir una nueva (caduca en {minutes} minutos y solo sirve una vez):\n\n"
        f"{link}\n\n"
        "Si no lo has pedido tú, ignora este correo: tu contraseña no cambia.\n\n"
        "Nexova Backoffice\n"
    )
    html = _html(
        name,
        [
            "Hemos recibido una solicitud para restablecer la contraseña de tu cuenta de Nexova.",
            f"El enlace caduca en {minutes} minutos y solo sirve una vez.",
            "Si no lo has pedido tú, ignora este correo: tu contraseña no cambia.",
        ],
        button=("Restablecer contraseña", link),
    )
    return Mail(to=to, subject="Restablece tu contraseña de Nexova", text=text, html=html)


def password_changed(to: str, name: str) -> Mail:
    lines = [
        "La contraseña de tu cuenta de Nexova se acaba de cambiar.",
        "Si has sido tú, no tienes que hacer nada. Si no, restablécela cuanto antes desde "
        "«¿Olvidaste tu contraseña?» en la página de inicio de sesión y avisa a un administrador.",
    ]
    text = f"Hola, {name}:\n\n" + "\n\n".join(lines) + "\n\nNexova Backoffice\n"
    return Mail(to=to, subject="Tu contraseña de Nexova ha cambiado", text=text, html=_html(name, lines))
