"""SUT: Mini-Defekt- und Testdaten-API (FastAPI + SQLite)."""
import os
import sqlite3
from datetime import date
from typing import Literal, Optional
from xml.etree import ElementTree as ET

from fastapi import Body, FastAPI, HTTPException, Response
from pydantic import BaseModel, Field, model_validator

DB_PATH = os.environ.get("DB_PATH", "data/app.db")
Status = Literal["offen", "in Analyse", "behoben", "geschlossen"]

TRANSITIONS = {
    "offen": {"in Analyse"},
    "in Analyse": {"behoben"},
    "behoben": {"geschlossen"},
    "geschlossen": {"offen", "in Analyse"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 4),
    status TEXT NOT NULL DEFAULT 'offen'
        CHECK (status IN ('offen','in Analyse','behoben','geschlossen'))
);
CREATE TABLE IF NOT EXISTS testdata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    defect_id INTEGER REFERENCES defects(id),
    name TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    CHECK (valid_from <= valid_to)
);
"""

app = FastAPI(title="Defekt- und Testdaten-API")


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.on_event("startup")
def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class DefectIn(BaseModel):
    title: str = Field(min_length=1, max_length=81)
    priority: int = Field(ge=1, le=4)


class DefectPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=80)
    priority: Optional[int] = Field(default=None, ge=1, le=4)
    status: Optional[Status] = None


class TestdataIn(BaseModel):
    project_id: int
    defect_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=80)
    valid_from: date
    valid_to: date

    @model_validator(mode="after")
    def check_range(self):
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to darf nicht vor valid_from liegen")
        return self


def row(r: sqlite3.Row) -> dict:
    return dict(r)


def get_defect(conn, defect_id: int) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM defects WHERE id = ?", (defect_id,)).fetchone()
    if r is None:
        raise HTTPException(404, f"Defekt {defect_id} nicht gefunden")
    return r


# ---- Projekte -------------------------------------------------------------
@app.post("/projects", status_code=201)
def create_project(p: ProjectIn):
    with connect() as conn:
        try:
            cur = conn.execute("INSERT INTO projects (name) VALUES (?)", (p.name,))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Projektname existiert bereits")
        return {"id": cur.lastrowid, "name": p.name}


@app.get("/projects")
def list_projects():
    with connect() as conn:
        return [row(r) for r in conn.execute("SELECT * FROM projects ORDER BY id")]


# ---- Defekte --------------------------------------------------------------
@app.post("/defects", status_code=201)
def create_defect(d: DefectIn):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO defects (title, priority) VALUES (?, ?)", (d.title, d.priority)
        )
        return row(get_defect(conn, cur.lastrowid))


@app.get("/defects")
def list_defects(status: Optional[Status] = None, priority: Optional[int] = None):
    if priority is not None and not 1 <= priority <= 4:
        raise HTTPException(422, "priority muss zwischen 1 und 4 liegen")
    sql, args = "SELECT * FROM defects WHERE 1=1", []
    if status is not None:
        sql += " AND status = ?"
        args.append(status)
    if priority is not None:
        sql += " AND priority = ?"
        args.append(priority)
    with connect() as conn:
        return [row(r) for r in conn.execute(sql + " ORDER BY id", args)]


@app.get("/defects/{defect_id}")
def read_defect(defect_id: int):
    with connect() as conn:
        return row(get_defect(conn, defect_id))


@app.patch("/defects/{defect_id}")
def update_defect(
    defect_id: int,
    patch: DefectPatch = Body(
        openapi_examples={
            "nur_status": {"summary": "Nur Status ändern", "value": {"status": "in Analyse"}},
            "nur_titel": {"summary": "Nur Titel ändern", "value": {"title": "Neuer Titel"}},
            "nur_prioritaet": {"summary": "Nur Priorität ändern", "value": {"priority": 2}},
        }
    ),
):
    with connect() as conn:
        current = get_defect(conn, defect_id)
        data = patch.model_dump(exclude_none=True)
        if "status" in data and data["status"] not in TRANSITIONS[current["status"]]:
            raise HTTPException(
                409, f"Statuswechsel {current['status']} -> {data['status']} nicht erlaubt"
            )
        if data:
            sets = ", ".join(f"{k} = ?" for k in data)
            conn.execute(f"UPDATE defects SET {sets} WHERE id = ?", (*data.values(), defect_id))
        return row(get_defect(conn, defect_id))


@app.delete("/defects/{defect_id}", status_code=204)
def delete_defect(defect_id: int):
    with connect() as conn:
        get_defect(conn, defect_id)
        used = conn.execute(
            "SELECT COUNT(*) FROM testdata WHERE defect_id = ?", (defect_id,)
        ).fetchone()[0]
        if used:
            raise HTTPException(409, f"Defekt wird von {used} Testdatensatz/-sätzen referenziert")
        conn.execute("DELETE FROM defects WHERE id = ?", (defect_id,))
    return Response(status_code=204)


# ---- Testdaten ------------------------------------------------------------
@app.post("/testdata", status_code=201)
def create_testdata(t: TestdataIn):
    with connect() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id = ?", (t.project_id,)).fetchone() is None:
            raise HTTPException(404, f"Projekt {t.project_id} nicht gefunden")
        if t.defect_id is not None:
            get_defect(conn, t.defect_id)
        overlap = conn.execute(
            "SELECT COUNT(*) FROM testdata WHERE project_id = ? "
            "AND valid_from <= ? AND valid_to >= ?",
            (t.project_id, t.valid_to.isoformat(), t.valid_from.isoformat()),
        ).fetchone()[0]
        if overlap:
            raise HTTPException(409, "Gültigkeit überlappt mit bestehendem Testdatensatz")
        cur = conn.execute(
            "INSERT INTO testdata (project_id, defect_id, name, valid_from, valid_to) "
            "VALUES (?, ?, ?, ?, ?)",
            (t.project_id, t.defect_id, t.name, t.valid_from.isoformat(), t.valid_to.isoformat()),
        )
        return row(conn.execute("SELECT * FROM testdata WHERE id = ?", (cur.lastrowid,)).fetchone())


@app.get("/testdata")
def list_testdata(project_id: Optional[int] = None):
    sql, args = "SELECT * FROM testdata", []
    if project_id is not None:
        sql += " WHERE project_id = ?"
        args.append(project_id)
    with connect() as conn:
        return [row(r) for r in conn.execute(sql + " ORDER BY id", args)]


# ---- Export ---------------------------------------------------------------
@app.get("/export/results.xml")
def export_xml():
    root = ET.Element("results")
    with connect() as conn:
        for r in conn.execute("SELECT * FROM defects ORDER BY id"):
            d = ET.SubElement(root, "defect", id=str(r["id"]))
            ET.SubElement(d, "title").text = r["title"]
            ET.SubElement(d, "priority").text = str(r["priority"])
            ET.SubElement(d, "status").text = r["status"]
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(content=xml, media_type="application/xml")
