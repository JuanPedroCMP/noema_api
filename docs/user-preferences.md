# User preferences

The authenticated `GET /api/v1/user_config/preferences` and
`PUT /api/v1/user_config/preferences` endpoints store account-scoped preferences
for the user identified by the bearer token. `PUT` replaces the preference
object and accepts:

```json
{
  "preferences": {
    "backupFrequency": "weekly",
    "timezone": "America/Sao_Paulo"
  }
}
```

`backupFrequency` is limited to `manual`, `daily`, `weekly`, or `monthly`.
`timezone`, when supplied, must be an IANA timezone name. Password-reset emails
display their timestamps in that timezone and in UTC; accounts without a saved
timezone use UTC.

The backup frequency is currently a saved preference only. The server does not
schedule backups. The app must initiate backups, including any “on app exit”
behavior; an exit event cannot be guaranteed by a server scheduler.

The language catalog is populated by the migration
`20261105_user_preferences_and_languages.sql`. English and Brazilian
Portuguese are marked as verified native translations; the other supported
response-language entries are marked as automatic translations.
