"""Entity summaries at ingestion (#201): written by the LLM, never «old summary + raw facts»."""
import asyncio
import inspect
from datetime import datetime, timezone

from test_control import client  # noqa: F401  (first: it sets the test environment before mimirsynth reads its settings)

import graphiti_core.graphiti as gg
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.utils.maintenance import node_operations

from mimirsynth import ingest


class FakeLLM:
    """Answers the summary prompt with a fixed text per entity, and records which prompt it was asked."""

    def __init__(self, summaries: dict[str, str]):
        self.summaries, self.prompts = summaries, []

    async def generate_response(self, messages, response_model=None, model_size=None, group_id=None, prompt_name=None, **kw):
        self.prompts.append(prompt_name)
        return {"summaries": [{"name": n, "summary": s} for n, s in self.summaries.items()]}


def _entity_and_edge():
    n = EntityNode(name="Lyra", group_id="g", labels=["Entity"], summary="Lyra is a cloud VPS.")
    edge = EntityEdge(source_node_uuid=n.uuid, target_node_uuid="x", name="RUNS", fact="Lyra runs Pangolin", group_id="g", created_at=datetime.now(timezone.utc))
    ep = EpisodicNode(name="e", group_id="g", source=EpisodeType.text, source_description="test", content="Lyra runs Pangolin.", valid_at=datetime.now(timezone.utc))
    return n, edge, ep


def _summarize(llm, node, edge, ep, skip):
    asyncio.run(node_operations._extract_entity_summaries_batch(llm, [node], ep, [], None, {node.uuid: [edge]}, skip_fact_appending=skip))


def test_graphiti_appends_raw_facts_by_default_and_asks_the_llm_with_the_flag():
    """The behaviour the fix depends on, pinned to the graphiti-core version MimirSynth embeds."""
    n, edge, ep = _entity_and_edge()
    llm = FakeLLM({"Lyra": "Lyra is a cloud VPS that runs Pangolin."})
    _summarize(llm, n, edge, ep, skip=False)
    assert n.summary == "Lyra is a cloud VPS.\nLyra runs Pangolin" and llm.prompts == []   # the shortcut: no LLM call at all

    n, edge, ep = _entity_and_edge()
    _summarize(llm, n, edge, ep, skip=True)
    assert n.summary == "Lyra is a cloud VPS that runs Pangolin." and llm.prompts == ["extract_nodes.extract_entity_summaries_from_episodes"]

    n, edge, ep = _entity_and_edge()
    _summarize(FakeLLM({"Lyra": "Lyra is a cloud VPS."}), n, edge, ep, skip=True)    # nothing durable is new: the summary stays
    assert n.summary == "Lyra is a cloud VPS."


def test_ingestion_wraps_graphiti_so_every_summary_goes_through_the_llm(monkeypatch):
    seen = []

    async def fake(*args, skip_fact_appending=False, **kwargs):
        seen.append(skip_fact_appending)
        return []
    monkeypatch.setattr(gg, "extract_attributes_from_nodes", fake)
    assert ingest.llm_summaries() is True
    asyncio.run(gg.extract_attributes_from_nodes(None, [], None, None, None, edges=[]))
    assert seen == [True]
    wrapped = gg.extract_attributes_from_nodes
    assert ingest.llm_summaries() is True and gg.extract_attributes_from_nodes is wrapped   # once per process, not wrapped twice


def test_a_graphiti_upgrade_that_drops_the_flag_is_reported(monkeypatch, caplog):
    async def old(clients, nodes, episode=None):
        return nodes
    monkeypatch.setattr(gg, "extract_attributes_from_nodes", old)
    assert ingest.llm_summaries() is False and gg.extract_attributes_from_nodes is old
    assert "summaries append raw facts again" in caplog.text


def test_the_graphiti_names_the_fix_relies_on_are_there():
    assert "skip_fact_appending" in inspect.signature(node_operations.extract_attributes_from_nodes).parameters
    assert hasattr(gg, "extract_attributes_from_nodes")   # add_episode calls it by the name graphiti.py imported
