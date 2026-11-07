**English** · [Español](Hechos-verificables)

# Verifiable facts

Many facts describe a system that can be asked: where a service runs, which address or version it has, whether it still exists. Left alone, they stay current until someone happens to contradict them. A **probe** checks a fact against a live system once a day through a **verifier**, and the recall says how recently each one was checked.

## Verifiers
A verifier is a small plugin: it gets the fact (subject, relation, value) and the probe's parameters, and answers **verified**, **refuted** (with the current value when it knows it) or **unverifiable**, with its evidence.
- **Built in**, only the example `json_inventory`: it reads a JSON file `{"key": "value"}` (or a list of values) that the instance can read, for example an inventory another tool exports into a mounted folder. Its setting is the file's path; each probe says which key to read.
- **Your own**: `.py` files in the folder named by `MIMIRSYNTH_VERIFIERS_DIR` ([[Environment variables]]), loaded at start. Loading external code is the administrator's explicit decision: without the variable, nothing else is loaded. A file:

```python
from mimirsynth.verify import Param, Result, Verifier, register

@register
class Cmdb(Verifier):
    id, label = "cmdb", "CMDB"
    config = [Param("url", "URL"), Param("token", "Token", secret=True)]   # per brain, set by its administrators
    params = [Param("ci", "Configuration item")]                          # per probe

    def check(self, fact, params):
        host = ...  # ask the CMDB at self.v["url"] with self.v["token"] for params["ci"]
        if host is None:
            return Result("unverifiable", "not in the CMDB")
        return Result("verified", f"CMDB: {host}") if host.lower() == fact["target"].lower() else Result("refuted", f"CMDB: {host}", host)
```

A verifier must be read-only and fast. An error or an unknown answer counts as **unverifiable**, with what went wrong.

## Settings and credentials
A brain administrator sets each verifier's settings for the brain (`PUT /api/brains/{slug}/verifiers/{id}` with `values`). Secret settings are stored sealed, like the wiki and notification secrets; they are never returned, and leaving one empty keeps the stored one. Probes run in a background job with those settings, never with the permissions of whoever reads the brain.

## Probes
On an entity's page ([[Entity page]]), each current fact has **Add probe** (or **Probe**, if it has one), for curators: choose the verifier and fill in what it asks, and its last result shows next to the fact (*Verified*, *Refuted*, *Unverifiable* or *Not checked yet*, with the evidence in its tooltip). [[Content quality]] → **Verification** lists every probe of the brain with its fact and last result, has **Check now**, and, for brain administrators, each verifier's settings; a secret one shows only whether it is set. Over the API, a curator attaches a probe to a current fact: `PUT /api/brains/{slug}/facts/{uuid}/probe` with `verifier` and `params`; `DELETE` removes it and `GET /api/brains/{slug}/probes` lists them with their last result. They are checked once a day (a probe not checked in 24 hours), and `POST …/probes/run` checks them now, up to 500 per run.

## What a result does
- **verified:** renews the fact's confirmation date, as confirming it by hand does, so its shelf life counts from then ([[Content quality]] → To review).
- **refuted:** a proposal that replaces the fact, with the evidence and, when the verifier gives one, the current value as its text ([[Proposals]] → Structured claims). It is decided by a person, like a correction. Nothing changes on its own, and while one is pending for the fact no other is created.
- **unverifiable:** nothing changes; the probe says why.

## In the recall
A fact with a probe carries `verification` (`state`, `checked_at`, `verifier`) in the recall's JSON. The context the agent reads adds «[verified on …]» or «[a system contradicted it on …]» next to it.
