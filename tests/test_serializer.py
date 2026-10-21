"""Testy serializacji programu do JSON i z powrotem (runda bezstratna)."""
from __future__ import annotations

import json

import pytest

from snapclick.core.model.blocks import BlockType
from snapclick.core.model.program import Program, ProgramError
from snapclick.core.model.serializer import load_program_dict, program_to_dict


def build_sample() -> Program:
    program = Program(name="Zakupy", window_title="MyApp")
    start = program.add_block(BlockType.START, 10, 20)
    click = program.add_block(BlockType.CLICK, 10, 90)
    click.params.update(template="buy_button", button="right",
                        threshold=0.85, double=True, on_fail="continue")
    ifb = program.add_block(BlockType.IF_FOUND, 10, 160)
    ifb.params.update(template="confirm", timeout=1.5)
    yes = program.add_block(BlockType.TYPE_TEXT, 40, 240)
    yes.params["text"] = "sztuk 50"
    loop = program.add_block(BlockType.WHILE_FOUND, 10, 320)
    loop.params.update(template="item", max_iterations=7)
    key = program.add_block(BlockType.KEY_PRESS, 40, 400)
    key.params["combo"] = "ctrl+v"

    program.set_socket(start.id, "next", click.id)
    program.set_socket(click.id, "next", ifb.id)
    program.set_socket(ifb.id, "then", yes.id)
    program.set_socket(ifb.id, "next", loop.id)
    program.set_socket(loop.id, "body", key.id)
    return program


def test_roundtrip_lossless():
    program = build_sample()
    templates = [{"id": "buy_button", "file": "assets/buy_button.png"}]
    data = program_to_dict(program, templates)
    text = json.dumps(data, ensure_ascii=False)
    loaded, loaded_templates = load_program_dict(json.loads(text))

    assert loaded.name == program.name
    assert loaded.window_title == program.window_title
    assert loaded_templates == templates
    assert set(loaded.blocks) == set(program.blocks)
    for bid, blk in program.blocks.items():
        other = loaded.blocks[bid]
        assert other.type == blk.type
        assert (other.x, other.y) == (blk.x, blk.y)
        assert other.next == blk.next
        assert other.then == blk.then
        assert other.otherwise == blk.otherwise
        assert other.body == blk.body
        # parametry jawne zachowane 1:1
        for k, v in blk.params.items():
            assert other.params.get(k) == v, f"param {k} bloczka {bid}"


def test_execution_order_survives_roundtrip():
    program = build_sample()
    loaded, _ = load_program_dict(program_to_dict(program))
    order_before = [b.id for b in program.execution_order()]
    order_after = [b.id for b in loaded.execution_order()]
    assert order_before == order_after
    assert len(order_before) == len(program.blocks)


def test_reject_unknown_schema():
    with pytest.raises(ValueError, match="wersja"):
        load_program_dict({"schema": 99, "blocks": []})


def test_reject_unknown_block_type():
    with pytest.raises(ValueError, match="typ bloku"):
        load_program_dict({"schema": 1, "blocks": [
            {"id": "x", "type": "quantum_leap"}]})


def test_reject_dangling_reference():
    with pytest.raises(ValueError, match="nieistniejący"):
        load_program_dict({"schema": 1, "blocks": [
            {"id": "a", "type": "start", "next": "ghost"}]})


def test_program_rejects_cycle():
    program = Program()
    a = program.add_block(BlockType.START)
    b = program.add_block(BlockType.WAIT)
    program.set_socket(a.id, "next", b.id)
    with pytest.raises(ProgramError, match="[Cc]ykl"):
        program.set_socket(b.id, "next", a.id)


def test_validate_detects_orphans_and_multiple_parents():
    program = Program()
    start = program.add_block(BlockType.START)
    orphan = program.add_block(BlockType.WAIT)
    a = program.add_block(BlockType.WAIT)
    b = program.add_block(BlockType.WAIT)
    # podwójny rodzic konstruujemy bezpośrednio na polach (set_socket ma
    # semantykę przenoszenia stosu i nie pozwoli na dwa wskazania)
    a.next = b.id
    start.next = b.id
    problems = program.validate()
    joined = " ".join(problems)
    assert "wiele gniazd" in joined
    orphans = [p for p in problems if "nie jest podłączony" in p]
    assert any(orphan.id in p for p in orphans)   # sierota zgłoszona
    assert any(a.id in p for p in orphans)        # a też nie ma rodzica
    assert not any(start.id in p for p in orphans)  # START nigdy nie sierota


def test_remove_block_removes_subgraph():
    program = Program()
    start = program.add_block(BlockType.START)
    outer = program.add_block(BlockType.REPEAT)
    inner = program.add_block(BlockType.WAIT)
    program.set_socket(start.id, "next", outer.id)
    program.set_socket(outer.id, "body", inner.id)
    removed = program.remove_block(outer.id)
    assert set(removed) == {outer.id, inner.id}
    assert program.blocks[start.id].next is None
