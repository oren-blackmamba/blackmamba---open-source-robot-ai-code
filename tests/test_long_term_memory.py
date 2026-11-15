import pytest

from ai_core.long_term_memory import PersistentEpisodicMemory


def test_episodes_survive_reopening_database(tmp_path):
    path = tmp_path / "humanis.sqlite3"
    memory = PersistentEpisodicMemory(str(path))
    memory.add(12.0, "goal", "moved cup to kitchen", ("cup", "kitchen"))
    memory.close()

    reopened = PersistentEpisodicMemory(str(path))
    recalled = reopened.recall("cup kitchen", k=1)
    assert len(recalled) == 1
    assert recalled[0].text == "moved cup to kitchen"
    assert reopened.last(1)[0].tags == ("cup", "kitchen")
    reopened.close()


def test_explicit_feedback_is_retrievable_and_persistent(tmp_path):
    path = tmp_path / "humanis.sqlite3"
    memory = PersistentEpisodicMemory(str(path))
    memory.add_feedback("find the red cup", -1, "The red cup is on the desk.")
    matches = memory.relevant_feedback("find red cup")
    assert matches[0]["rating"] == -1
    assert "desk" in matches[0]["correction"]
    memory.close()


def test_feedback_rating_is_validated(tmp_path):
    memory = PersistentEpisodicMemory(str(tmp_path / "humanis.sqlite3"))
    with pytest.raises(ValueError):
        memory.add_feedback("test goal", 0)
    memory.close()
