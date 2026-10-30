**English** · [Español](Seguridad-y-doble-factor)

# Security and two-factor

The **Security** section of administration: the policy of own accounts. All values apply without a restart.

## Settings
| Setting | Default | What it does |
|---|---|---|
| **Minimum password length** | 12 (8–64) | Applied when creating or changing passwords |
| **Failed attempts before locking** | 5 (3–20) | After that many consecutive errors, the account is temporarily locked |
| **Lockout duration** | 15 min (1–1440) | How long the lock lasts |
| **Require two-factor** | No | "Yes, everyone" forces anyone signing in with a password to set up a second factor |
| **Validity of invitations and recovery links** | 7 days (1–30) | After the period the link stops working |

## Password policy
Besides length, a password is rejected if it:
- is a **common password** (`password`, `contraseña`, `qwerty…`, the application's name…);
- is made of **a single repeated character** or is a **sequence**, including one that wraps around (`abcdefghijkl`, `987654321098`, `…yzab…`);
- uses **fewer than 5 distinct characters**;
- **contains your email or your name**.

Every password field lists these rules and ticks them off as you type; while one is missing, the button says what it is. This applies to the first-run wizard, invitations and resets, the temporary password screen and [[My account]]. Passwords are stored with **argon2id**.

## Locking and attempts
- Failed password **and** second-factor attempts count towards the same lock. A locked account cannot sign in with a passkey either.
- There is also a **request limit** per IP address and per account on sign-in, two-factor, passkeys, password recovery and first-run setup ("too many attempts" answers). Its counters are kept **in the database**, so they are shared between processes and a restart does not reset them. If the database fails, it falls back to an in-memory counter: access is never left unprotected.
- The sign-in screen **does not reveal which accounts exist**: the error message is always the same and so is the response time.
- An administrator can **unlock** an account early from the user's page ([[Administer users]]).

## Two-factor (TOTP)
Each person can enable it in [[My account]] with an authenticator app; they are given **10 single-use recovery codes**.

**What signing in with two-factor looks like:** password → "Two-step verification" screen (6-digit code from the app, a recovery code or, if the account has one, **Use passkey**) → in. The permission to send the code lasts 5 minutes. An app code **cannot be reused**.

## Passkeys
A passkey (WebAuthn) lets a person sign in with their device's **fingerprint, face or PIN** instead of typing a password. Each person adds theirs in [[My account]] → Security → **Passkeys**.
- **Sign in with a passkey**, on the sign-in screen, enters without a password. After a password, **Use passkey** works as the second step, like an app code.
- A passkey requires the device to verify the person, so **it counts as two-factor**, also when two-factor is mandatory.
- Only the **public key** is stored; the private key never leaves the device. A sign counter detects cloned keys, and each challenge is single-use and expires.
- Removing a passkey asks for the password (if the account has one) and is refused if it is the person's **only way in**: they must set a password or link a provider first.

> **It needs `MIMIRSYNTH_PUBLIC_URL` over HTTPS.** A passkey only works on the domain it was created on (the host of the public URL). Set it before anyone registers a passkey: changing the domain later invalidates them all, so keep the password as a fallback. See [[Environment variables]].

### Requiring it of everyone
Set **Require two-factor** to "Yes". From then on, anyone signing in **with a password** without a second factor **only sees the screen to set one up** (an authenticator app **or** a passkey, plus the option to sign out) until they do; the API also blocks them. While it is required, nobody can disable it.
- **It does not affect OIDC sign-ins**: there the second factor your identity provider applies governs.
- Enable your own two-factor first and save your recovery codes **before** requiring it.

### If someone loses it
If they lose their phone and recovery codes, the administrator uses **Remove two-factor** on their page. It removes the authenticator app **and their passkeys** and closes their sessions; they can set it up again afterwards.

## Sessions
Sessions are a signed cookie. All of an account's sessions are closed when: it changes its password, an administrator disables it, the person accepts a reset link, or they press "Sign out on other devices".
