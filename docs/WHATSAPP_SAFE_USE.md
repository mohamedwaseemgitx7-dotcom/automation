# WhatsApp QR connection – safe-use guide

The QR (linked-device) connection is **unofficial**. WhatsApp can log out, restrict or ban a number that is
automated this way, and nothing in this project can guarantee it won't happen. What we *can* do is behave like a
normal, careful business user and avoid everything WhatsApp's systems are known to act on.

## What the software already does
| Behaviour | Why |
|---|---|
| Replies only to people who message first | Unsolicited messages are the main reason numbers get reported and banned |
| Only 5 approved contacts get AI replies | Small, known audience during testing |
| No bulk send, no broadcast, no contact scraping, no group automation | These are the patterns WhatsApp targets |
| Marks the message read, shows "typing…", then replies after a natural pause (2–9 s) | Normal chat behaviour and a better customer experience. It is **not** a way to hide automation |
| Max 6 incoming messages per minute per contact are answered | Stops reply loops with another bot |
| Polite fallback + handoff to the owner when unsure | Fewer annoyed customers, fewer reports |
| Owner can pause all replies, pause one chat, disconnect, or delete the session | Quick stop if anything looks wrong |

## What the owner should do
1. **Use a spare number first**, not the business's main number. An old, already active number is better than a brand-new SIM.
2. Keep the phone **online and charged**. The linked device stops working if the phone is offline for about 14 days.
3. **Don't link the same number to other bot tools** at the same time.
4. Start slowly: the 5 test contacts for a few days, then real customers.
5. Never paste links or files the customer didn't ask for. Don't send the same text to many people.
6. If WhatsApp shows any warning or logs the device out, **stop automation** and switch to manual replies.
7. For long-term production, plan the move to the official WhatsApp Cloud API (adapter already kept separate).

## Not built, on purpose
No anti-detection tricks: no fake device fingerprints, no message spinning, no randomised identities, no
bypassing of limits. These break WhatsApp's terms and are exactly what gets accounts banned.

## Future: catalogue with prices
When the owner supplies a verified price list, it becomes part of the knowledge ZIP (CSV/XLSX). The agent then
quotes those prices and the claim check keeps blocking any price that is not in the file. Product photos can be
sent as images later (Phase 3).
