<p align="center">
  <img src="assets/banner.svg" alt="Schema Forge — schema-aware synthetic data" width="100%"/>
</p>

<p align="center">
  <a href="https://github.com/Athul-S-369/Schema-Forge">
    <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=22&duration=3500&pause=900&color=3DDC97&center=true&vCenter=true&multiline=true&repeat=true&width=720&height=70&lines=Forge+valid+data+from+your+schema;Zipf+%C2%B7+Normal+%C2%B7+Skewed+distributions;Same+seed+%E2%87%92+same+dataset" alt="Typing animation" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-0b1220?style=for-the-badge&logo=python&logoColor=3ddc97" alt="Python"/>
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0-0b1220?style=for-the-badge&logo=sqlalchemy&logoColor=38bdf8" alt="SQLAlchemy"/>
  <img src="https://img.shields.io/badge/MySQL-Ready-0b1220?style=for-the-badge&logo=mysql&logoColor=5eead4" alt="MySQL"/>
  <img src="https://img.shields.io/badge/Faker-Powered-0b1220?style=for-the-badge&logo=fastapi&logoColor=a78bfa" alt="Faker"/>
  <img src="https://img.shields.io/badge/License-MIT-0b1220?style=for-the-badge&logoColor=fbbf24" alt="License"/>
</p>

<p align="center">
  <b>Schema Forge</b> turns a real database schema into realistic, constraint-safe synthetic data.<br/>
  No hand-written Faker rule sheets. No broken foreign keys. Same seed → same dataset.
</p>

<p align="center">
  <img src="assets/terminal.svg" alt="CLI preview" />
</p>

---

## Why Schema Forge?

Most generators ask you to **describe** the schema twice — once in SQL, again as Faker recipes.  
Schema Forge **reads** your SQLAlchemy models, builds a relationship graph, and emits rows that stay valid.

| Pillar | What it does |
| :--- | :--- |
| **Schema understanding** | Introspects tables, FKs, UNIQUEs, and CHECKs into a live graph |
| **Constraint awareness** | Honors enums, bounds, uniqueness — never invents illegal values |
| **Referential integrity** | Topo-sorts tables so every FK points at a real parent |
| **Realistic distributions** | Zipf / normal / skewed / lognormal — not flat random noise |
| **Deterministic seeds** | `--seed 42` today equals `--seed 42` tomorrow |

> **v1 focus:** those five pillars only. Streaming scale, exporters, anonymization, plugins — later.

---

## Animated pipeline

<p align="center">
  <img src="assets/pipeline.svg" alt="Introspect → Topo-sort → Constrain → Distribute → Seed & Emit" width="100%"/>
</p>

```text
  models.Base ──► SchemaGraph ──► dependency order ──► SynthEngine ──► DB / JSON
                       │                                    │
                       ├─ FK edges                          ├─ Zipf parent picks
                       ├─ CHECK hints                       ├─ unique ledgers
                       └─ UNIQUE keys                       └─ stable SeedContext
```

---

## Quick start

### 1. Install

```bash
git clone https://github.com/Athul-S-369/Schema-Forge.git
cd Schema-Forge
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

Create a `.env` (or export vars):

```env
DATABASE_URL=mysql+pymysql://root:password@localhost/amazon_marketplace
CREATE_TABLES=true
```

### 3. Inspect the graph

```bash
python run_synth_engine.py --inspect
```

You’ll see generation order like:

```text
country -> settlement_policy -> seller -> brand -> product -> ... -> review
```

### 4. Generate

```bash
# In-memory dry run (no DB writes)
python run_synth_engine.py --dry-run --seed 42 --rows 5 --dump sample.json

# Insert into MySQL
python run_synth_engine.py --seed 42 --fk-distribution zipf

# Custom table sizes
python run_synth_engine.py --seed 7 --counts "customer=50,product=100,orders=80"
```

### Classic hand-tuned seeder

Still available for the Amazon marketplace demo:

```bash
python generate_sample_data.py
```

---

## Project layout

```text
Schema-Forge/
├── assets/                  # Animated SVG banner & pipeline
├── synth_engine/            # Focused v1 engine (the five pillars)
│   ├── schema.py            # Relationship graph + CHECK parsing
│   ├── constraints.py       # UNIQUE / validity ledger
│   ├── distributions.py     # Zipf · normal · skewed · lognormal
│   ├── rng.py               # Deterministic SeedContext
│   ├── values.py            # Type-aware column synthesis
│   └── generator.py         # Orchestrator + ORM insert
├── models.py                # SQLAlchemy Amazon marketplace schema
├── scheme_sql_file.sql      # Reference DDL
├── run_synth_engine.py      # CLI for the engine
├── generate_sample_data.py  # Classic Faker seeder
└── requirements.txt
```

---

## CLI cheat sheet

| Flag | Meaning |
| :--- | :--- |
| `--inspect` | Print the relationship graph & exit |
| `--seed N` | Deterministic RNG / Faker seed |
| `--rows N` | Default rows per table |
| `--counts a=1,b=2` | Per-table overrides |
| `--fk-distribution` | `zipf` · `skewed` · `uniform` |
| `--dry-run` | Generate in memory only |
| `--dump path.json` | Write dry-run rows to disk |

---

## Determinism that matters for tests

```python
from models import Base
from synth_engine import SynthEngine, SeedContext

engine = SynthEngine.from_metadata(Base, seed=42, default_rows=10)
store_a = engine.generate_all()

engine = SynthEngine.from_metadata(Base, seed=42, default_rows=10)
store_b = engine.generate_all()

assert store_a.rows["customer"] == store_b.rows["customer"]  # same seed → same data
```

Child streams are derived with a **stable hash** (`sha256(seed:table)`), so table order doesn’t scramble reproducibility.

---

## Domain schema (demo)

Built around an **Amazon-style marketplace**: geography, sellers, products, carts, orders, payments, shipments, inventory, returns, settlements, reviews — **35 tables**, wired with real FKs and CHECK constraints.

<p align="center">
  <img src="https://img.shields.io/badge/tables-35-3ddc97?style=flat-square&labelColor=0b1220" alt="35 tables"/>
  <img src="https://img.shields.io/badge/engine-schema--aware-38bdf8?style=flat-square&labelColor=0b1220" alt="schema-aware"/>
  <img src="https://img.shields.io/badge/integrity-FK%20safe-5eead4?style=flat-square&labelColor=0b1220" alt="FK safe"/>
  <img src="https://img.shields.io/badge/seeds-deterministic-fbbf24?style=flat-square&labelColor=0b1220" alt="deterministic"/>
</p>

---

## Roadmap (intentionally later)

<details>
<summary><b>Not in v1 — click to expand</b></summary>

- Streaming / chunked generation for millions of rows  
- Data validation reports  
- Multi-format exporters  
- Anonymization mode  
- Benchmark profiles & edge-case packs  
- API mock backends & synthetic event streams  
- Plugin system  

</details>

---

## Contributing

1. Fork the repo  
2. Create a feature branch (`git checkout -b feat/amazing`)  
3. Keep changes focused on the five pillars unless proposing a roadmap item  
4. Open a PR  

---

## License

MIT — forge freely.

---

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&size=16&duration=2800&pause=1200&color=94A3B8&center=true&vCenter=true&width=560&height=32&lines=Built+for+tests.+Forged+from+schemas." alt="Footer typing" />
</p>

<p align="center">
  <sub>★ Star the repo if Schema Forge saved you from broken FKs</sub>
</p>
