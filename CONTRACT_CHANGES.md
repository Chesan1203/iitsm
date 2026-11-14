# Contract changes

The contract (`CONTRACT.md`) is frozen at tag `contract-v1`. To propose a change, do NOT edit
the contract. Add one line below, message the group chat, and wait for a thumbs-up from the
other three. P1 then applies the change to the skeleton.

Format: `YYYY-MM-DD | what | why | who is affected | status`

2026-11-14 | SlaEventType.WARNING split into RESPONSE_WARNING and RESOLUTION_WARNING | tracker keeps separate response/resolution warned flags; one WARNING plus the unique (incident, event type) rule dropped the second warning | persistence (sla_events.event_type values), services (SlaMonitorJob) | applied in T6
