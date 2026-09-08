"""Words the engine must never learn *into* and must protect at rewrite.

This is a pragmatic, plug-replaceable dictionary. In a production Kivi
deployment this would be the system lexicon (potentially per-locale);
here it is a curated list of high-frequency English words that ASR
already renders reliably. Rewriting any of them risks corrupting
ordinary prose, so the engine refuses them as correction *targets* and
treats them as "real-word homophone risk" at rewrite time -- rewriting
them requires supporting context.

Note that ``kiwi`` is deliberately present: it is a dictionary word (a
fruit), which is exactly why rewriting it to ``Kivi`` requires the
user's product context ("<word> service") to appear.
"""

# Deduplicated, alphabetised within categories. If you edit this, run
# tests -- some behaviour tests depend on "kiwi" being present.
_COMMON = """
a about above after again against all am an and any are as at
be because been before being below between both but by
can cannot could do does doing done down during
each few for from further
had has have having he her here hers herself him himself his how
i if in into is it its itself
just
let me more most my myself
no nor not
of off on once only or other ought our ours ourselves out over own
same she should so some such
than that the their theirs them themselves then there these they this those through to too
under until up
very
was we were what when where which while who whom why with would
you your yours yourself yourselves

ask call called calls email emailed emails invite invited invites mail
make makes made meet meeting meetings message messages msg ping pings
reply replied replies review reviewed reviews send sent sends check
checked take taken takes give gave gives get got gets

day days week weeks month months year years today tomorrow yesterday
morning afternoon evening night monday tuesday wednesday thursday
friday saturday sunday january february march april may june july
august september october november december time times hour hours

work works working team teams project projects service services app
apps product products company companies client clients customer
customers notes note task tasks todo

good great bad nice new old big small long short high low first last
next best better worse different easy hard

food eat eats lunch dinner breakfast snack fruit fruits vegetable
apple apples banana bananas mango oranges grape grapes kiwi melon
berry berries peach pear plum watermelon papaya guava litchi cherry
rice bread milk eggs sugar salt tea coffee water juice
"""

COMMON_WORDS = frozenset(_COMMON.split())
