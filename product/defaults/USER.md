# User profile

This file is the durable profile shared by the local agent. Keep only stable,
user-approved facts here. Do not store API keys, cookies, passwords, raw private
messages or speculative personality labels.

## Operator

- Name:
- Preferred language: Chinese
- Working style:
- Approval boundaries:

## Operating portfolio

Subjects and accounts are maintained by the native portfolio registry. Keep
only stable strategy facts here when the user explicitly approves them:

```yaml
subjects:
  - display_name: ""
    stable_positioning_facts: []
```

- Conversations are global and may compare or aggregate every authorized
  subject and platform account.
- An account id is selected only for a concrete external operation and recorded
  in its receipt; it is never a conversation permission boundary.

## Provider policy

- Prefer ByteDance/Volcengine capabilities when available.
- Ask before paid batches, publishing, sending messages or other external-state changes.
- Keep task IDs and output receipts for generated media.
