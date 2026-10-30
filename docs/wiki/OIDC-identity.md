**English** · [Español](Identidad-OIDC)

# OIDC identity

The **Identity** section of administration. It lets people sign in with one or several **external identity providers** (PocketID, Keycloak, Authentik, Entra ID, Google…) as well as with their own account. It is **optional**: MimirSynth works without it.

> OIDC sign-in **does not replace** the account system: each person still has their account, and each provider is **linked** to it. By default only people who already have an account or invitation can sign in.

## Providers
The section lists the **sign-in providers**. Each one has its **own** connection, automatic sign-up policy and group roles, and shows **its own button** ("Sign in with …") on the access screen. You can **add**, **edit**, **test the connection** and **delete** them.

1. At your provider, register an **application (OIDC client)**. Each provider card shows its **return URL** (`…/api/auth/callback/<identifier>`; for the one imported from a previous version it is still `…/api/auth/callback`), with a copy button.
2. Press **Add provider** and fill in:
   | Field | What to put |
   |---|---|
   | **Identifier** | Short name used in the URLs (lowercase, numbers, hyphens). **It cannot be changed** afterwards |
   | **Button label** | Text of the sign-in button ("Sign in with *label*") |
   | **OIDC issuer** | Provider base URL; it must publish `/.well-known/openid-configuration` |
   | **Client ID** | The registered application's identifier |
   | **Client secret** | Stored **encrypted** and never shown again. When editing, leave it empty to keep the saved one |
   | **Scopes** | Permissions requested (default `openid profile email`) |
   | **Active** | A disabled provider is not offered on the access screen |
3. **An issuer that does not respond cannot be saved**, so that nobody is locked out by a mistake. **Test connection** reads the provider's discovery document.
4. The **Public URL** (shared setting, below the list) is used to build the return URLs.

**Deleting** a provider unlinks the identities of the people who used it. It is **refused** if someone would be left with no way to sign in (no password and no other provider): give them a password or link another provider first.

> **Upgrading from 0.4 or earlier:** the single provider you had configured (from the interface or from the `MIMIRSYNTH_OIDC_*` variables) is imported **once**, on the first start, as the provider `oidc`, with the **same return URL**: you do not need to change anything at your provider. From then on, manage it only here; the variables are no longer read and you can remove them from `.env`.

## Who can sign in
Someone signs in through a provider if they meet **one** of these conditions:
1. Their identity is already **linked** to an account.
2. They have an **active or invited** account with **the same email**, **verified** by the provider: it is then linked automatically. An invited account becomes active.
3. Their email is in **Instance administrators** and the provider marks it as **verified**: an administrator account is created.
4. The provider has **automatic sign-up** enabled and their **verified** email is from one of its **allowed domains**.

In any other case they will see "Your account is not registered on this instance". A **disabled** account does not sign in.

### Unverified emails
Some providers do not mark the email as verified (Entra ID, for example). For them there is **Accept unverified emails**, so that invitations can be accepted through that provider. With it enabled:
- An unverified email **only links to an invitation** (an account that has no password or provider yet).
- It **never** links to an account that is already **active**. That person sees "You already have an account with that email. Sign in as usual and link this provider from My account → Security", and links it from [[My account]] after signing in.
- It never creates an account: neither **Instance administrators** nor **automatic sign-up** accept an unverified email.

### Per-provider settings
| Setting | Default | Notes |
|---|---|---|
| **Accept unverified emails** | No | Only for providers that do not mark the email as verified. Anyone who can register someone else's email at the provider could accept that person's invitation. **Do not enable it unless you trust the provider** |
| **Automatic sign-up** | No (invited only) | The account is created without an invitation, only for the allowed domains |
| **Allowed domains** | empty | Domains (comma-separated, e.g. `example.com`) to which automatic sign-up applies. Empty = none |
| **Initial access** | empty | Brains that automatically registered people join, as `brain:role` (see below) |

### Shared settings
| Setting | Default | Notes |
|---|---|---|
| **Instance administrators** | empty | Emails (comma-separated) that get an administrator account the first time they sign in through a provider, only with an email the provider marks as verified |
| **Account management** | empty | URL of your provider's page where password, passkeys and two-factor are managed; it is linked from [[My account]] |

**Automatic sign-up:** the new account is a **user** (not administrator) with the provider's **initial access** and whatever its groups grant, and nothing else. It is **never** applied to unverified emails, even if you enable "Accept unverified emails".

### Initial access
A comma-separated list of `brain:role`, for example `docs:reader, wiki:contributor`, that a person registered through **automatic sign-up** receives:
- Only the roles `reader` and `contributor` are allowed: anyone from those domains gets them without anyone reviewing them, and what they propose follows the brain's usual path (a curator or the decider).
- It is applied **once**, when the account is created, as an ordinary membership recorded in the [[Audit log]] (`member.set`, `via=oidc-default:<provider>`). An administrator can change or remove it in [[Administer users]], and no later sign-in restores it.
- If a group grants a **higher role** on the same brain, the higher one wins.
- Saving the provider refuses other roles, repeated brains and brains that do not exist; a brain deleted later is skipped.
- It does not apply to invitations, which bring their own roles.

## Groups and roles
If a provider sends each person's **groups** in a field of its identity, you can give roles automatically (each provider has its own rules).

| Setting | Default | What it does |
|---|---|---|
| **Groups claim** | `groups` | Name of the field with the groups (the provider must include it, with the right scope) |
| **Administrators group** | empty | Members of this group are **instance administrators**. Anyone who leaves the group loses the role at their next sign-in, unless they are the last administrator |
| **Roles by group** | empty | `group=brain:role` rules separated by commas. Roles: `reader`, `contributor`, `curator`, `admin` |

Example for **Roles by group**: `curators=docs:curator, readers=docs:reader`.

How it works:
- Applied **on every sign-in**.
- They **grant** the role if the person does not already have an **equal or higher** one, and **never lower** an existing one. By group, **"owner" is never granted**.
- They are also **revoked**: when someone **leaves a group**, the next time they sign in they lose what that group gave them (the administrator role or the brain role). If the group had **raised** a role (for example from reader to curator), they go back to the previous one.
- What was set **by hand** is **never touched**: roles that already existed before 0.5, roles an administrator sets or changes afterwards in [[Administer users]], and roles the person already had at an equal or higher level.
- Safeguards: the **last active administrator is never revoked**; and **if the provider does not send the groups field** nothing is revoked (a configuration mistake must not leave everyone without access). When the administrator role is revoked, that person's open sessions are closed.
- Rules with a brain that does not exist or an invalid role are ignored.

## Linking several providers to one account
Each person can link and unlink providers in [[My account]] → Security → **Linked identities**. Linking goes through the provider and adds it to the current account; an identity that already belongs to another account is rejected. The last way to sign in cannot be unlinked.

## The local administrator and mixed mode
With a provider active, **accounts with passwords keep working**: they serve as an emergency access if the provider goes down. Keep at least one administrator account with a password (and two-factor).

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| The provider will not save | The issuer does not respond or does not publish the discovery document (use "Test connection") |
| "invalid redirect_uri" at the provider | The registered return URL does not match the one shown on the provider card (scheme, domain, path) |
| "Your account is not registered" | No account/invitation with that email, the email is not verified, or the domain is not allowed |
| "You already have an account with that email…" | The provider sent an unverified email that matches an active account: sign in as usual and link the provider from [[My account]] → Security |
| Signs in without the expected roles | The provider does not send the groups field, or the claim name does not match |
| Lost a role after leaving a group | Expected: roles granted by a group are revoked when you leave it |
| The first sign-in fails and the next works | The provider took too long to answer the discovery request; retry |
