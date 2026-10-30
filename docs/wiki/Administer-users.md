**English** · [Español](Administrar-usuarios)

# Administer users

The **Users** section of administration (instance administrator only). It manages MimirSynth's **own accounts**: sign-ups, invitations, roles, locks and removals.

## The table
One row per person: **user** (name and email), **role** (administrator or user), **access** methods (password and linked OIDC providers), **status**, number of **brains** and **last sign-in**. With sorting and filters per column (search by name or email, filter by role and status).

| State | Meaning |
|---|---|
| **Invited** | Created but has not yet accepted the invitation or signed in |
| **Active** | Can sign in |
| **Disabled** | Cannot sign in (their API tokens do not work either) |
An account may also appear as temporarily **locked** after too many failed attempts.

If no mail server is configured, you will see an attention notice at the top, **"No mail server"**, with a link to [[SMTP email]]: without it, invitation and recovery links are copied by hand.

## Creating a user
**Create user** button:
- **Email** and **Name**.
- **Instance administrator** (checkbox): manages users, settings and all brains.
- **Access**, two modes:
  - **Invitation:** a **single-use link** is generated for the person to choose their password. If email is configured, it is also sent. **Copy it at that moment**: it is only shown on creation (you can generate another later).
  - **Temporary password:** you set a password and the person **must change it on sign-in**.
Links expire after **7 days** (adjustable in [[Security and two-factor]]).

## A user's page
Clicking a row opens their side panel:
- **Data:** state, labels (administrator, locked, password, 2FA, providers), email and dates.
- **Instance administrator** (switch). You cannot change your own role.
- **Disable / Enable.**
- **New invitation link** (if they have not accepted yet) or **Reset password** (generates a link for them to choose a new one; if email is set up, it is sent).
- **Unlock** (if locked).
- **Remove two-factor**: for someone who lost their phone and recovery codes. It removes their authenticator app **and their passkeys**, and signs out their sessions.
- **Sign out its sessions.**
- **Delete.**
- **Brains:** all their memberships with their role (change it with the selector), **Remove** from a brain and **Add to a brain**. Someone registered automatically through an OIDC provider arrives with that provider's **initial access** ([[OIDC identity]]): it is an ordinary membership, so you can change or remove it here and no later sign-in restores it.

## Deleting a user
It **anonymises** the account: its email and name are erased, access, sessions and tokens are removed, and the email is **freed** so it can be invited again. Their **proposals and the audit log are kept** as "Deleted user".

## Protections
- You cannot disable or delete yourself, or remove your own administrator role.
- The **last active administrator** cannot be disabled, deleted or demoted.
- Every action on this screen is recorded in the [[Audit log]].

## The invitation path
1. The administrator creates the user (invitation mode) and hands over the link.
2. The person opens it (`/acceso/<code>`), sees their email, chooses a name and password, and **signs in directly**.
3. The link is invalidated (single use) and previous sessions of that account are closed.
An expired or used link is replaced by generating another from the user's page.

## Recovering the password
On the sign-in screen, **"Forgot your password?"** sends a link by email (only if SMTP is configured; the answer is always the same so as not to reveal which accounts exist). Without email, the administrator generates the link from the user's page ("Reset password").
