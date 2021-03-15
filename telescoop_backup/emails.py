from smtplib import SMTPException

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_email(
    template_directory,
    file_name,
    subject,
    receiver,
    subject_id="",
    data=None,
    attachment=None,
):
    txt = render_to_string(f"{template_directory}/emails/txt/{file_name}.html", data)
    html = render_to_string(f"{template_directory}/emails/html/{file_name}.html", data)
    try:
        msg = EmailMultiAlternatives(
            subject=subject_id + subject,
            body=txt,
            to=receiver,
        )

        msg.attach_alternative(html, "text/html")
        msg.extra_headers["X-Mailgun-Tag"] = [file_name]
        if attachment:
            msg.attach(attachment["name"], attachment["content"], "application/pdf")
        msg.send()
    except SMTPException as e:
        print("There was an error sending an email: ", e)


def email_user_activation(request, user):
    data = {
        "title": "Vérifier votre email",
        "url": (
            f"{settings.FRONT_END_URL}/user/activation?email={user.email}"
            f"&activation_key={user.activation_key}"
        ),
    }

    send_email(
        template_directory="telescoop_backup",
        file_name="user_activation",
        subject=data["title"],
        data=data,
        receiver=[user.email],
    )
