"""False-positive stress corpus.

A fixed set of ordinary English sentences that must survive the engine
untouched *after* the demo seed has been applied. Every intervention on
any sentence in this list is a false positive: the engine was taught
about "Aaditya", "Kivi", "paneer" and "UrZoo", and none of the sentences
below mentions any of those.

The corpus is diverse on purpose -- work, personal, technical, everyday
prose, punctuation, weekday names, common food words including "kiwi"
the fruit, common names that are phonetically near but not equal to
taught ones -- so a false positive here would flag a real risk in
production. The specific number of false positives is reported in the
evaluation summary and any hits are printed with their reasons.
"""

STRESS_CORPUS: list[str] = [
    # -- ordinary work speak ------------------------------------------------
    "Please schedule the quarterly review for next Wednesday afternoon.",
    "The engineering team shipped the release without any regressions.",
    "Can you send me the updated slide deck by end of day?",
    "I will forward the meeting notes once the client signs off.",
    "The client asked for a discount on the annual contract.",
    "Our Q4 revenue projection is slightly ahead of the plan.",
    "The onboarding document needs a proofread before Monday.",
    "Please add me to the calendar invite for the sync tomorrow.",
    "The design review moved from Thursday to Friday morning.",
    "The support team has resolved every open ticket from last week.",

    # -- personal messages --------------------------------------------------
    "Remember to pick up milk, bread and eggs on the way home.",
    "The kids have football practice on Saturday at ten in the morning.",
    "Grandma called earlier; please ring her back before dinner.",
    "The plumber is coming on Tuesday between two and four.",
    "The car needs its service done before the road trip next month.",
    "Book the flights for the weekend as soon as prices drop.",
    "Do not forget the umbrella; the forecast says rain all week.",
    "The concert tickets go on sale Friday at nine in the morning.",
    "Please water the plants while we are away over the holiday.",
    "We should try that new restaurant in the neighbourhood soon.",

    # -- technical / prose --------------------------------------------------
    "The build failed because a dependency was missing from the lockfile.",
    "The migration script must run before the application boots.",
    "Cache invalidation and naming things are famously hard problems.",
    "The distributed system tolerates a single node failure at a time.",
    "The database index made the slow query fast almost overnight.",
    "The API returns a 429 when the rate limit has been exceeded.",
    "The pull request has three approvals and is ready to merge.",
    "The unit tests all pass but one integration test is flaky.",
    "The logs show the request timed out after thirty seconds.",
    "The retry policy uses exponential backoff with jitter.",

    # -- prose containing near-miss lookalikes ------------------------------
    "Please ask Aditi to prepare the summary before the review.",
    "I love kiwi fruit in a summer salad with mint and lime.",
    "Panner is a common misspelling but paneer is the standard form.",
    "Arvind wrote the first draft; Ananya edited the second one.",
    "The new intern Aditi joined the design team last Monday.",
    "The market has fresh kiwi, mango and papaya this weekend.",

    # -- classic English literature (Pride and Prejudice, opening) ---------
    "It is a truth universally acknowledged that a single man in "
    "possession of a good fortune must be in want of a wife.",
    "However little known the feelings or views of such a man may be "
    "on his first entering a neighbourhood.",
    "This truth is so well fixed in the minds of the surrounding "
    "families that he is considered the rightful property of some one "
    "or other of their daughters.",

    # -- everyday questions and imperatives --------------------------------
    "What time is the meeting on Tuesday?",
    "Please close the door when you leave the office.",
    "Can you confirm the address before I send the parcel?",
    "The weather has been unusually warm for this time of year.",
    "The gym opens at six in the morning on weekdays.",
    "Do you want tea or coffee with breakfast?",
    "The library closes early on Sundays and public holidays.",
    "The show starts at eight; try to arrive fifteen minutes earlier.",
    "The traffic on the main road was terrible this morning.",
    "The neighbours are having a garage sale over the weekend.",
]
