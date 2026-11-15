"""How a turn's prompt is put together (04-agents.md section 7)."""

from twyf.contract.turns import TURN_MODELS
from twyf.db.repos.agents import AgentRow
from twyf.db.repos.definitions import DefinitionVersion, SkillVersion

CITE = "cite-passages"


def name_line(agent: AgentRow) -> str:
    line = f"Your name is {agent.name}."
    if agent.agent_kind == "translator" and agent.specialty and agent.specialty != "generic":
        line += f" Your speciality is {agent.specialty}."
    return line


def render(
    agent: AgentRow, definition: DefinitionVersion, turn_type: str, skills: dict[str, SkillVersion], *, rules: str
) -> tuple[str, str]:
    """Returns (system_prompt, instructions).

    system_prompt: the rules of agents.md, the definition's resolved prompt, then the name line.
    instructions: the turn's skill, preceded by cite-passages when the turn lists it."""
    system_prompt = "\n\n".join([rules.strip(), definition.resolved_prompt.strip(), name_line(agent)])
    listed = TURN_MODELS[turn_type][2]
    ordered = ([CITE] if CITE in listed else []) + [s for s in listed if s != CITE]
    instructions = "\n\n".join(skills[slug].body.strip() for slug in ordered)
    return system_prompt, instructions
