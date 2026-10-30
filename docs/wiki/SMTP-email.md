**English** · [Español](Correo-SMTP)

# SMTP email

The **Email (SMTP)** section of administration. It configures the mail server MimirSynth uses to send **invitations**, **password recovery links** and, if you set up an email channel, **alert notifications**. It is optional: without it, the administrator copies the links by hand from the user's page, and alerts can go through the other channels (or just the bell).

## Settings
| Setting | Default | Notes |
|---|---|---|
| **SMTP server** | empty | Server address (`smtp.example.com`) |
| **Port** | 587 | Typical: 587 (STARTTLS), 465 (SSL) or 25 |
| **Encryption** | STARTTLS | STARTTLS (587), SSL/TLS (465) or none (trusted networks only) |
| **User** | empty | Empty if the server does not require authentication |
| **Password** | — | Stored **encrypted** and not shown again |
| **Sender** | empty | The address shown as sender (`mimirsynth@example.com`) |

## Testing
Under the settings there is a field for a **destination email** and the **Send test** button. If something fails, the message gives the reason (authentication, encryption, connection…). The test uses the **already saved** configuration: save your changes before testing. Check that it arrives **before** depending on it.

## What is sent
- **Invitation**: "You have been invited to MimirSynth", with a single-use link to choose the password.
- **Reset**: "Reset your MimirSynth password", with another link. If you did not ask for it, it can be ignored.
- **Alerts**: an **Email** channel under *Administration → Notifications* sends the alerts it is subscribed to (AI model or graph not responding, failed ingestion or job, document source error, account lockout…) to the recipients you list, through this same server. Alerts never include memory content.

Invitations and resets go out in the recipient's language (or the instance's default; see [[Settings reference]]). Links expire after 7 days by default ([[Security and two-factor]]).

## Common providers
| Provider | Server | Port / encryption |
|---|---|---|
| Own server (Postfix…) | yours | 587 STARTTLS, or 25 unencrypted on a trusted network |
| Gmail / Google Workspace | `smtp.gmail.com` | 587 STARTTLS, with an **app password** |
| Microsoft 365 | `smtp.office365.com` | 587 STARTTLS |
| Transactional services | the one the service indicates | normally 587 or 465 |

## If the emails do not arrive
- Check the spam folder and that the **sender** is an address your server allows.
- With providers requiring **strong authentication** (Gmail, Microsoft), use an app password or a dedicated sending user.
- If the server presents an invalid certificate, encryption will fail: use a correct certificate.
- "Forgot your password?" **always answers the same** (so as not to reveal which accounts exist): if nothing arrives, email is not configured, the account does not exist or the limit of 3 requests per hour was exceeded.
- An alert email that does not arrive shows up as a failed delivery in *Administration → Notifications*, where it can be retried by hand.
