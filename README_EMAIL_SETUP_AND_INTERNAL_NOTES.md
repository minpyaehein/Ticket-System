# Email setup and staff-only internal notes

## Email setup
1. Open **Email Notifications** as Admin.
2. Choose Gmail if the sender is a Gmail account. The page will use `smtp.gmail.com`, port `587`, and `STARTTLS`.
3. Enter the full Gmail address and a Google **App Password** (not the normal account password).
4. Save settings, then enter a recipient address under **Send test email** and test delivery.
5. If you use another provider, choose Outlook / Microsoft 365 or Other email provider and review Advanced SMTP settings.

The saved `stmp.cmp` value is a malformed/unresolvable hostname. The Gmail preset corrects it to `smtp.gmail.com`, but delivery still requires the correct email address, app password, internet/DNS and provider access.

## Internal notes
In a staff ticket conversation, click **Internal note** to switch from public reply mode. The submit button changes to **Add internal note**. Internal notes are only visible to Admin and Agent, are filtered from Customer reply APIs, and do not trigger customer email notifications. Public replies continue to use the New comment or reply notification rule.

## Password reset confirmation
Admin reset actions now show a centered confirmation dialog with **OK** and **Cancel**. The email is issued only after confirmation. SMTP errors remain visible as actionable messages if the mail server cannot be reached.
