**English** · [Español](Mi-cuenta)

# My account

Your profile, your security, your API tokens and your activity. Open it from your **avatar and name** at the bottom of the side bar; the button next to them **signs you out** in one click. The sections are in the list on the left (on mobile, on top), grouped as **Account** (Profile, Security, Email summary), **Access** (API tokens) and **History** (Activity). Under that list there is also a highlighted **Sign out** button.

## Profile
- **Avatar:** upload an image (PNG, JPEG or WebP, up to **1 MB**) or **Remove** it to go back to the identity provider's one or to your initials.
- **Display name:** how you appear in the application. If left empty, the identity provider's name is used.
- **Language:** English or Spanish. It is saved to your account and applies on any device. It sets the language of the interface and of your emails, and also of what the **API and the MCP server** answer to your API tokens: error messages, the MCP tools' descriptions and the headings of the recall context. A client that sends an `Accept-Language` header gets that language instead. Stored memory is never translated: facts, episodes and documents come back as they were written. See [[Connect agents]].
- **Account:** your email, your instance role (administrator or user), when the account was created, your last sign-in and the **brains** you can access with your role in each.

## Security
### Password
- If you already have one, **change it** (it asks for the current one). The form shows the rules (minimum length, 12 by default; not your email or name; not common or a sequence; at least 5 different characters) and ticks them off as you type. See [[Security and two-factor]].
- If so far you only signed in through your identity provider (OIDC), you can **set a password** to also sign in directly, in case the provider is unavailable.
- Changing it **signs you out on all other devices**.

### Linked identities
The external providers (OIDC) you can sign in with. **Link** another one to have more than one way in, or **unlink** one you no longer use. Linking goes through the provider and is added to this account; an identity that already belongs to another account is rejected, and you cannot unlink your only way to sign in (set a password first). See [[OIDC identity]].

### Passkeys
Sign in with your device's **fingerprint, face or PIN** instead of typing the password. A passkey already **counts as two-factor**.
1. Press **Add passkey**.
2. Give it a **Passkey name** (laptop, phone, USB key…) and, if you have a password, **Confirm your password**.
3. Press **Create passkey** and complete the gesture on your device.

The list shows each passkey with its creation date and last use, marked **synced** when your platform or password manager keeps a copy of it (so it also works on your other devices). **Remove** asks for your password and is refused if that passkey is your only way in. On the sign-in screen, use **Sign in with a passkey**. If the browser says it does not support passkeys, use another browser or device. Passkeys only work on the instance's public address; if the administrator changes it, add them again.

### Two-step verification (two-factor)
It adds to the password a 6-digit code from an **authenticator app** (Aegis, 2FAS, Google Authenticator, Bitwarden…). It is only available if you have your own password.

**Enabling:**
1. Press **Enable two-factor** and confirm your password.
2. **Scan the QR code** with the app (or type the key by hand if you cannot scan).
3. Enter the 6-digit code the app shows and press **Activate**.
4. **10 recovery codes** are shown. **Save them** (password manager or paper): each one works once if you lose your phone and **they are not shown again**.

**Afterwards:** when signing in with a password, the app's code (or a recovery code) is asked for as well; if you also have a passkey, you can use it for that step instead. App codes cannot be reused.

**Managing:** *Generate new codes* (the old ones stop working) or *Disable* (they ask for the password and a code). If the administrator **requires** two-factor, it cannot be disabled. If you lose your phone **and** the codes, an administrator can remove it for you ([[Administer users]]); that also removes your passkeys.

> Two-factor protects **password** access. If you sign in through your identity provider (OIDC), the verification rules are applied by that provider.

### Sessions
**Sign out on other devices** (this session stays open) if you think someone else has it open, and **Sign out**. There is also a link to your account at the identity provider, if the administrator configured it.

## Email summary
A periodic email with what changed in your brains, for when you do not open the application every day. In **Email summary**, choose for each brain **Never**, **Every day** or **Every week**, and under **When** the hour, the day of the week (for weekly summaries) and your **time zone** (the browser's, the first time). **See an example** shows what a summary of your brains would say now.

- **What it says:** for each brain, how many facts are new and how many were invalidated, and how many documents were added. If you are a **curator or above**, also what waits for you: proposals and corrections to review (and how old the oldest is), documents with errors, possible contradictions and facts to review. Each line links to its page, already in that brain.
- **Only counts and links, never the content of the memories.** To read it, follow the link.
- **Nothing to say, nothing sent:** a brain with nothing new and the same pending counts as in its last summary is left out, and if no brain is left, no email arrives.
- **One email** covers every brain due at that moment. The first one counts from when you subscribed. If the instance was stopped, it sends one summary when it comes back, not one per missed day.
- It goes to your account's email, in your language, and needs the instance's email ([[SMTP email]]). Losing access to a brain removes its summary.

## API tokens
Tokens let **plugins and agents** access a brain without using your password.
- Choose the **brain**, a **name** (for example "Claude Code laptop") and a **role**.
- Each token is valid for **a single brain** and **never has more role than you** (maximum *curator*; none administers the instance).
- The token (`mst_…`) **is shown only once** when created. Copy it at that moment.
- Choose when it **expires** (30, 90 or 365 days, or never, unless the instance sets a maximum) and its **scope**: recall, documents and propose.
- You will see your tokens with their prefix, scope, expiry and last use; **Rotate** gives a new one and keeps the old one working for a grace period, and **Revoke** removes the ones you no longer use. See «Expiry and rotation» in [[Connect agents]].
Usage in [[Connect agents]].

## Recent activity
Your history of actions (sign-ins, proposals, fact and vocabulary changes, tokens…) with the date and a readable summary. It can be sorted and searched.
