from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models import ActiveIngredient, Article, Product
from app.models.entities import ArticleStatus
from app.services.export_service import build_icsr_records
from app.services.pipeline import product_name_list


def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _combo_product(db):
    amox = ActiveIngredient(name="amoxicillin", inn="amoxicillin", atc_code="J01CA04")
    clav = ActiveIngredient(
        name="clavulanic acid", inn="clavulanic acid", atc_code="J01CR02"
    )
    db.add_all([amox, clav])
    db.flush()
    product = Product(
        name="Co-amoxiclav",
        inn="amoxicillin",
        brands=["Augmentin"],
        synonyms=[],
        active_ingredients=[amox, clav],
    )
    db.add(product)
    db.flush()
    return product, amox, clav


def test_product_carries_multiple_apis():
    """The combination case the single inn column could not express."""
    db = session()
    product, amox, clav = _combo_product(db)
    assert {i.name for i in product.active_ingredients} == {
        "amoxicillin",
        "clavulanic acid",
    }


def test_one_api_spans_many_products():
    db = session()
    _, amox, _ = _combo_product(db)
    other = Product(name="Amoxil", inn="amoxicillin", brands=[], synonyms=[])
    other.active_ingredients = [amox]
    db.add(other)
    db.flush()
    assert {p.name for p in amox.products} == {"Co-amoxiclav", "Amoxil"}


def test_api_names_widen_the_screening_match_set():
    db = session()
    product, _, _ = _combo_product(db)
    names = [n.lower() for n in product_name_list(product)]
    assert "clavulanic acid" in names
    assert "amoxicillin" in names


def test_icsr_record_carries_api_tags_for_export():
    db = session()
    product, _, _ = _combo_product(db)
    article = Article(
        product_id=product.id,
        pmid="99887766",
        title="Anaphylaxis after co-amoxiclav",
        status=ArticleStatus.APPROVED_FOR_SUBMISSION,
    )
    db.add(article)
    db.flush()
    records = build_icsr_records(db, [article])
    assert records[0]["active_ingredients"] == ["amoxicillin", "clavulanic acid"]
    assert records[0]["product"] == "Co-amoxiclav"


def test_untagged_product_falls_back_to_legacy_inn():
    db = session()
    product = Product(name="Legacy", inn="metformin", brands=[], synonyms=[])
    db.add(product)
    db.flush()
    article = Article(
        product_id=product.id,
        pmid="11112222",
        title="Legacy case",
        status=ArticleStatus.APPROVED_FOR_SUBMISSION,
    )
    db.add(article)
    db.flush()
    records = build_icsr_records(db, [article])
    assert records[0]["active_ingredients"] == ["metformin"]
