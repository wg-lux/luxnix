# NoIP Managed Mail Infos

Within your mail server you will need to use the following settings to send an email:
Outgoing SMTP Server: smtp-auth.no-ip.com
Port Number: 25, 465, 587, 3325 (preferred)
Username: yourdomain.com@noip-smtp
Password: ThePasswordYouCreated

[!info]

> Many email servers reject all emails from domains that aren’t authenticated by an SPF record. So you will need to add this record to your domain.
> If your domain is managed by No-IP, the SPF record can be added in your No-IP account from the DNS Records page. Click Modify for your domain, then on the Hostname page, click TXT. At the bottom of the TXT page, in the box labeled “Data”, paste the SPF record provided below:
> v=spf1 include:no-ip.com -all
> Finally, click Add
> If your DNS is managed elsewhere you’ll have to add that same record with your DNS provider.

- [x] Add txt record (done)

_NoIP Postfix guide_: https://www.noip.com/support/knowledgebase/configure-postfix-work-alternate-port-smtp

# Variables for setup

mail.noip.com
ssl on
authentication on
webmaster@endo-reg.net
port 465

# NixOS Postfix Example

services.postfix = {
enable = true;
relayHost = "smtp.gmail.com";
relayPort = 587;
config = {
smtp_use_tls = "yes";
smtp_sasl_auth_enable = "yes";
smtp_sasl_security_options = "";
smtp_sasl_password_maps = "texthash:${config.sops.secrets."postfix/sasl_passwd".path}"; # optional: Forward mails to root (e.g. from cron jobs, smartd) # to me privately and to my work email:
virtual_alias_maps = "inline:{ {root=you@gmail.com, you@work.com} }";
};
};
