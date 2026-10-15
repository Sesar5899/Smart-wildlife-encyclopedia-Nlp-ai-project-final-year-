"""Private publishing console for the wildlife catalog."""

from __future__ import annotations

import hmac
import json
import re
import secrets
import time
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from flask import (
    Blueprint, Response, abort, flash, g, jsonify, redirect,
    render_template, request, session, stream_with_context, url_for,
)

import embeddings
import llm
import rag
import provenance
from config import Config
from db import (
    animal_chat_key, delete_animal, fuzzy_search_animals, get_all_animals,
    get_animal_by_id, get_animals_with_aliases, get_categories, save_animal,
)
from portal_collections import (
    delete_collection_record, filter_ecosystems, filter_protected_areas,
    get_ecosystem, get_protected_area, load_ecosystems, load_protected_areas,
    save_collection_record,
)


bp = Blueprint("admin", __name__, url_prefix="/admin")
UPLOAD_ROOT = Path(__file__).resolve().parent / "static" / "uploads"

COLLECTIONS = {
    "ecosystems": {
        "title": "ဂေဟစနစ်များ",
        "singular": "ဂေဟစနစ်",
        "loader": load_ecosystems,
        "getter": get_ecosystem,
        "image_dir": "ecosystems",
        "detail_endpoint": "ecosystem_detail",
        "fields": [
            ("name_mm", "မြန်မာအမည်", "text"),
            ("name", "အင်္ဂလိပ်အမည်", "text"),
            ("code", "စနစ်ကုဒ်", "text"),
            ("description_mm", "ဖော်ပြချက်", "textarea"),
            ("in_realm_mm", "နယ်ပယ်", "text"),
            ("in_biome_mm", "ဇီဝဒေသ", "text"),
            ("in_functional_group_mm", "လုပ်ဆောင်ချက်အုပ်စု", "text"),
            ("in_state_region_mm", "တိုင်း/ပြည်နယ်", "text"),
            ("national_iucn_status", "IUCN အဆင့်", "text"),
            ("temperature_text_mm", "ပျမ်းမျှအပူချိန်", "text"),
            ("precipitation_text_mm", "မိုးရေချိန်", "text"),
            ("soil_text_mm", "မြေဆီလွှာ", "text"),
            ("elevation_text_mm", "အမြင့်", "text"),
            ("date_assessed", "အကဲဖြတ်သည့်နေ့", "text"),
            ("year_published", "ထုတ်ဝေသည့်နှစ်", "text"),
            ("distribution_mm", "ဖြန့်ကျက်တည်ရှိမှု", "textarea"),
            ("native_biota_mm", "မူရင်း ဇီဝအစုအဖွဲ့", "textarea"),
            ("abiotic_environment_mm", "ဇီဝမဲ့ပတ်ဝန်းကျင်", "textarea"),
            ("key_processes_and_interactions_mm", "အဓိက လုပ်ငန်းစဉ်များနှင့် ဆက်နွယ်မှု", "textarea"),
            ("threats_mm", "ပျက်စီးစေသည့် အချက်များ", "textarea"),
            ("assessment_summary_mm", "ဂေဟစနစ် အကဲဖြတ်ချက်", "textarea"),
            ("collapse_definition_mm", "ဂေဟစနစ် ပျက်စီးဆုံးရှုံးမှု သတ်မှတ်ချက်", "textarea"),
            ("species_fauna_mm", "တွေ့ရှိရသော သတ္တဝါများ", "textarea"),
            ("species_flora_mm", "တွေ့ရှိရသော အပင်များ", "textarea"),
        ],
    },
    "protected_areas": {
        "title": "ကာကွယ်ထိန်းသိမ်းနယ်မြေများ",
        "singular": "ကာကွယ်ထိန်းသိမ်းနယ်မြေ",
        "loader": load_protected_areas,
        "getter": get_protected_area,
        "image_dir": "protected-areas",
        "detail_endpoint": "protected_area_detail",
        "fields": [
            ("name_mm", "မြန်မာအမည်", "text"),
            ("name", "အင်္ဂလိပ်အမည်", "text"),
            ("designation_mm", "သတ်မှတ်အမျိုးအစား", "text"),
            ("status_mm", "အခြေအနေ", "text"),
            ("description_mm", "ဖော်ပြချက်", "textarea"),
            ("in_state_region_mm", "တိုင်း/ပြည်နယ်", "text"),
            ("boundary_mm", "နယ်နိမိတ်", "textarea"),
            ("established_year", "တည်ထောင်သည့်နှစ်", "text"),
            ("designaton_date", "သတ်မှတ်ကြေညာသည့်နေ့", "text"),
            ("eval_year", "အကဲဖြတ်သည့်နှစ်", "text"),
            ("area_ha", "ဧရိယာ (ဟက်တာ)", "text"),
            ("area_acre", "ဧရိယာ (ဧက)", "text"),
            ("protection_level_mm", "ကာကွယ်မှုအဆင့်", "text"),
            ("bio_unit_mm", "ဇီဝနယ်မြေ", "text"),
            ("bio_unit", "ဇီဝနယ်မြေ ကုဒ်/အမျိုးအစား", "text"),
            ("habitat_types_mm", "နေထိုင်ရာပတ်ဝန်းကျင်", "textarea"),
            ("governance_type_mm", "အုပ်ချုပ်မှုပုံစံ", "textarea"),
            ("management_authority_mm", "စီမံခန့်ခွဲသူ", "textarea"),
            ("main_purposes_mm", "အဓိက ရည်ရွယ်ချက်များ", "textarea"),
            ("natural_resources_mm", "သဘာဝရင်းမြစ်နှင့် ဇီဝမျိုးစုံမျိုးကွဲ", "textarea"),
            ("tourism_mm", "ခရီးသွားနှင့် လေ့လာရေး", "textarea"),
            ("species_fauna_mm", "တွေ့ရှိရသော သတ္တဝါများ", "textarea"),
            ("species_flora_mm", "တွေ့ရှိရသော အပင်များ", "textarea"),
        ],
    },
}


def user_is_admin(user) -> bool:
    if not user:
        return False
    return bool(user.get("is_admin")) or user.get("email", "").lower() in Config.ADMIN_EMAILS


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("current_user"):
            return redirect(url_for("login", next=request.path))
        if not user_is_admin(g.current_user):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    token = session.get("admin_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["admin_csrf_token"] = token
    return token


def require_csrf() -> None:
    expected = session.get("admin_csrf_token", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        abort(400, "Invalid form token")


def _detected_extension(header: bytes) -> str | None:
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    return None


def save_photo(upload, kind: str) -> str | None:
    """Validate image bytes and return a local public URL."""
    if not upload or not upload.filename:
        return None
    header = upload.stream.read(16)
    upload.stream.seek(0)
    extension = _detected_extension(header)
    if not extension:
        raise ValueError("JPEG, PNG သို့မဟုတ် WebP ဓာတ်ပုံကိုသာ တင်နိုင်ပါသည်။")
    destination_dir = UPLOAD_ROOT / kind
    destination_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    upload.save(destination_dir / filename)
    return f"/static/uploads/{kind}/{filename}"


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9\u1000-\u109f]+", "_", value.strip())
    return value.strip("_")[:140]


def submitted_sources():
    """Return a validated, ordered list from the repeatable source editor."""
    labels = request.form.getlist("source_label")
    urls = request.form.getlist("source_url_item")
    sources = []
    for position, raw_url in enumerate(urls, start=1):
        url = raw_url.strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Source URL {position} သည် http/https URL အပြည့်အစုံ ဖြစ်ရမည်။")
        label = labels[position - 1].strip() if position <= len(labels) else ""
        sources.append({"label": label or f"Source {position}", "url": url})
    return sources


def existing_sources(record):
    sources = record.get("sources") or record.get("source_urls") or []
    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except (TypeError, json.JSONDecodeError):
            sources = []
    sources = [item for item in sources if isinstance(item, dict) and item.get("url")]
    if not sources and record.get("source_url"):
        sources = [{
            "label": record.get("source_name") or "Original source",
            "url": record["source_url"],
        }]
    return sources


def _index_published_record(content_kind, record, *, previous_key=None):
    """Index one saved record online, while keeping publishing recoverable."""
    record_key = (
        animal_chat_key(record) if content_kind == "animal" else record.get("slug")
    )
    if previous_key and str(previous_key) != str(record_key):
        embeddings.remove_record(content_kind, previous_key)
    if not embeddings.online_enabled():
        flash(
            "မှတ်တမ်းကို သိမ်းပြီးပါပြီ၊ သို့သော် vector index မပြည့်သေးပါ။ "
            "Admin process တွင် OPENAI_API_KEY သတ်မှတ်ပြီး Retrieval Pipeline မှ "
            "Full index ပြန်တည်ဆောက်ပါ။",
            "error",
        )
        return None
    try:
        result = embeddings.index_record(
            content_kind, record_key, rag.record_passages(content_kind, record)
        )
    except embeddings.EmbeddingError as exc:
        flash(f"မှတ်တမ်း သိမ်းပြီးသော်လည်း OpenAI vector index မအောင်မြင်ပါ — {exc}", "error")
        return None
    flash(
        f"OpenAI vector index: passage {result['passages']} ခု ပြည့်စုံပါသည် "
        f"({result['new_vectors']} new).",
        "success",
    )
    return result


@bp.route("")
@admin_required
def dashboard():
    section = request.args.get("section", "animals")
    query = request.args.get("q", "").strip()
    # The library search is the member search.  A plain casefolded substring
    # over three columns missed everything Myanmar text needs: it could not see
    # an alias, so ကျားတိမ် found no clouded leopard; it could not normalise, so
    # a name carrying an invisible U+200C matched nothing; and it never looked
    # at a record's own text.  Both sides now run the same code.
    if section == "animals":
        records = (
            fuzzy_search_animals(query, limit=None) if query else get_all_animals()
        )
    elif section in COLLECTIONS:
        catalog = list(COLLECTIONS[section]["loader"]())
        records = (
            filter_ecosystems(catalog, query) if section == "ecosystems"
            else filter_protected_areas(catalog, query)
        )
    else:
        abort(404)
    return render_template(
        "admin/dashboard.html",
        section=section,
        records=records,
        query=query,
        counts={
            "animals": len(get_all_animals()),
            "protected": sum(
                1 for item in get_all_animals() if item.get("protection_status_my")
            ),
            "ecosystems": len(load_ecosystems()),
            "protected_areas": len(load_protected_areas()),
        },
        csrf_token=csrf_token(),
    )


@bp.route("/api/search")
@admin_required
def search_suggestions():
    """Use the dashboard matchers for all three Content Studio sections."""
    section = request.args.get("section", "animals")
    query = request.args.get("q", "").strip()
    if section != "animals" and section not in COLLECTIONS:
        abort(404)
    if not query:
        return jsonify([])

    if section == "animals":
        matches = fuzzy_search_animals(query, limit=5)
        return jsonify([{
            "label": item["name_my"],
            "subtitle": item["name_en"],
            "url": url_for("admin.animal_form", animal_id=item["id"]),
        } for item in matches])

    catalog = COLLECTIONS[section]["loader"]()
    matches = (
        filter_ecosystems(catalog, query) if section == "ecosystems"
        else filter_protected_areas(catalog, query)
    )[:5]
    return jsonify([{
        "label": item.get("name_mm") or item.get("name") or "",
        "subtitle": item.get("name") or "",
        "url": url_for("admin.collection_form", kind=section, slug=item["slug"]),
    } for item in matches])


@bp.route("/animals/new", methods=["GET", "POST"])
@bp.route("/animals/<int:animal_id>/edit", methods=["GET", "POST"])
@admin_required
def animal_form(animal_id=None):
    animal = get_animal_by_id(animal_id) if animal_id else None
    if animal_id and not animal:
        abort(404)
    if request.method == "POST":
        require_csrf()
        values = request.form.to_dict()
        if not values.get("name_my", "").strip() or not values.get("name_en", "").strip():
            flash("မြန်မာအမည်နှင့် အင်္ဂလိပ်အမည် နှစ်ခုလုံး ဖြည့်ပါ။", "error")
        else:
            try:
                sources = submitted_sources()
                cover_url = save_photo(request.files.get("photo"), "animals")
                male_url = save_photo(request.files.get("male_photo"), "animals")
                female_url = save_photo(request.files.get("female_photo"), "animals")
                existing_cover = values.get("existing_image_url", "")
                existing_male = values.get("existing_male_image_url", "")
                existing_female = values.get("existing_female_image_url", "")
                values["male_image_url"] = (
                    "" if values.get("remove_male_photo") else male_url or existing_male
                )
                values["female_image_url"] = (
                    "" if values.get("remove_female_photo") else female_url or existing_female
                )
                primary = "" if values.get("remove_photo") else cover_url or existing_cover
                values["image_url"] = primary or values["male_image_url"] or values["female_image_url"]
                values["source_urls"] = json.dumps(sources, ensure_ascii=False)
                values["source_name"] = sources[0]["label"] if sources else ""
                values["source_url"] = sources[0]["url"] if sources else ""
                valid_urls = {source["url"] for source in sources}
                values["field_sources"] = {}
                previous_field_sources = (animal or {}).get("field_sources") or {}
                for field in provenance.FIELD_LABELS:
                    if not values.get(field):
                        continue
                    chosen = list(dict.fromkeys(
                        url for url in request.form.getlist(f"field_source.{field}")
                        if url in valid_urls
                    ))
                    field_changed = animal and str(values.get(field, "")).strip() != str(animal.get(field) or "").strip()
                    if (field_changed and chosen == previous_field_sources.get(field, [])
                            and request.form.get(f"field_source_confirmed.{field}") != "1"):
                        chosen = []
                    if chosen:
                        values["field_sources"][field] = chosen
                saved_id = save_animal(values, animal_id)
                flash("တိရစ္ဆာန်မှတ်တမ်းကို ထုတ်ဝေပြီးပါပြီ။ AI လက်ထောက်က ချက်ချင်း အသုံးပြုနိုင်ပါသည်။", "success")
                saved_record = get_animal_by_id(saved_id)
                _index_published_record("animal", saved_record)
                return redirect(url_for("admin.animal_form", animal_id=saved_id))
            except (ValueError, LookupError) as exc:
                flash(str(exc), "error")
        animal = {**(animal or {}), **values}
        animal["sources"] = locals().get("sources", existing_sources(animal))
        if animal_id is not None:
            animal["id"] = animal_id
    return render_template(
        "admin/animal_form.html",
        animal=animal or {},
        categories=get_categories(),
        sourceable_fields=provenance.FIELD_LABELS,
        csrf_token=csrf_token(),
        is_new=animal_id is None,
    )


@bp.post("/animals/<int:animal_id>/delete")
@admin_required
def animal_delete(animal_id):
    require_csrf()
    record = get_animal_by_id(animal_id)
    if not delete_animal(animal_id):
        abort(404)
    if record:
        embeddings.remove_record("animal", animal_chat_key(record))
    flash("တိရစ္ဆာန်မှတ်တမ်းကို ဖျက်ပြီးပါပြီ။", "success")
    return redirect(url_for("admin.dashboard", section="animals"))


@bp.route("/<kind>/new", methods=["GET", "POST"])
@bp.route("/<kind>/<path:slug>/edit", methods=["GET", "POST"])
@admin_required
def collection_form(kind, slug=None):
    config = COLLECTIONS.get(kind)
    if not config:
        abort(404)
    record = config["getter"](slug) if slug else None
    if slug and not record:
        abort(404)
    if request.method == "POST":
        require_csrf()
        values = {field: request.form.get(field, "").strip() for field, _, _ in config["fields"]}
        values["slug"] = request.form.get("slug", "").strip() or slugify(
            values.get("name") or values.get("name_mm") or ""
        )
        if not values["slug"] or not (values.get("name") or values.get("name_mm")):
            flash("အမည်နှင့် URL slug ကို ဖြည့်ပါ။", "error")
        else:
            try:
                sources = submitted_sources()
                existing_images = [] if request.form.get("remove_photos") else list((record or {}).get("image_urls") or [])
                new_images = [
                    saved for upload in request.files.getlist("photos")
                    if (saved := save_photo(upload, config["image_dir"]))
                ]
                images = existing_images + new_images
                values["image_urls"] = images
                values["image_url"] = images[0] if images else None
                values["source_urls"] = sources
                values["source_name"] = sources[0]["label"] if sources else "Admin published"
                values["source_url"] = sources[0]["url"] if sources else ""
                saved_slug = save_collection_record(kind, values, slug)
                flash(f"{config['singular']} မှတ်တမ်းကို ထုတ်ဝေပြီးပါပြီ။ AI လက်ထောက်က အသစ်ပြင်ထားသော အချက်အလက်ကို ချက်ချင်း အသုံးပြုပါမည်။", "success")
                rag_kind = "ecosystem" if kind == "ecosystems" else "protected-area"
                saved_record = config["getter"](saved_slug)
                _index_published_record(
                    rag_kind, saved_record, previous_key=slug if slug else None
                )
                return redirect(url_for("admin.collection_form", kind=kind, slug=saved_slug))
            except ValueError as exc:
                flash(str(exc), "error")
        record = {**(record or {}), **values}
        record["sources"] = locals().get("sources", existing_sources(record))
    elif record is not None:
        record = {**record, "sources": existing_sources(record)}
    return render_template(
        "admin/collection_form.html",
        kind=kind,
        config=config,
        record=record or {},
        csrf_token=csrf_token(),
        is_new=slug is None,
    )


@bp.post("/<kind>/<path:slug>/delete")
@admin_required
def collection_delete(kind, slug):
    if kind not in COLLECTIONS:
        abort(404)
    require_csrf()
    if not delete_collection_record(kind, slug):
        abort(404)
    rag_kind = "ecosystem" if kind == "ecosystems" else "protected-area"
    embeddings.remove_record(rag_kind, slug)
    flash(f"{COLLECTIONS[kind]['singular']} မှတ်တမ်းကို ဖျက်ပြီးပါပြီ။", "success")
    return redirect(url_for("admin.dashboard", section=kind))


# --------------------------------------------------------------------------
# Retrieval console — the pipeline, running on a real record
# --------------------------------------------------------------------------

def _pipeline_record(key):
    """The record one subject key points at, as ``(kind, record)``.

    Loaded through the same accessors the chat endpoints use.  A species has
    to come from ``get_animal_by_id``, which attaches the portal fields: the
    catalog listing omits them, and tracing against the listing would quietly
    score a smaller record than the chat actually retrieves over.
    """
    kind, _, ident = (key or "").partition(":")
    if kind == "animal":
        record = get_animal_by_id(ident) if str(ident).isdigit() else None
    elif kind == "ecosystem":
        record = get_ecosystem(ident)
    elif kind == "protected-area":
        record = get_protected_area(ident)
    else:
        return None, None
    return (kind, record) if record else (None, None)


def _subject_page_url(subject):
    """Where the console says a hand-over would send the member.

    Built from the chat's own function so the console can never show a
    destination the member would not actually be given.
    """
    from app import subject_page_url

    return subject_page_url(subject)


def _final_answer(kind, record, name, question, trace):
    """The reply this question actually produces, when no model is involved.

    Three of the four branches are written by the site itself, so the console
    can show the member's exact wording without generating anything.  Built
    from the same functions the chat endpoints call, never a second copy.
    Returns ``(text, images)``, or ``None`` when the model has to be asked.
    """
    from app import OUT_OF_SCOPE_NOTICE, photo_answer, redirect_notice_text

    outcome = trace["outcome"]
    if outcome == "handover":
        return redirect_notice_text(name, trace["subject"]), []
    if outcome == "photos":
        return photo_answer(question, kind, record, name) or (OUT_OF_SCOPE_NOTICE, [])
    if outcome == "refusal":
        return OUT_OF_SCOPE_NOTICE, []
    return None


PREVIEW_DIMS = 12


def _vector_rows(question_vector, passages, passage_vectors, selected):
    """Each passage's stored vector beside its similarity, strongest first.

    Scored through ``rag.semantic_scores`` so the console can never show a
    similarity the retriever did not itself compute.  ``selected`` marks the
    passages the retriever actually sent on, which is what ties the vectors
    shown here to the answer shown below them.
    """
    scores = {
        id(passage): score
        for score, passage in rag.semantic_scores(
            question_vector, passages, passage_vectors
        )
    }
    chosen = {passage.label for passage in selected}
    rows = [
        {
            "label": passage.label,
            "preview": (vector or [])[:PREVIEW_DIMS],
            "rest": max(len(vector or []) - PREVIEW_DIMS, 0),
            "cosine": None if id(passage) not in scores
                      else round(scores[id(passage)], 4),
            "selected": passage.label in chosen,
        }
        for passage, vector in zip(passages, passage_vectors)
    ]
    rows.sort(
        key=lambda row: row["cosine"] if row["cosine"] is not None else -1,
        reverse=True,
    )
    return rows


@bp.route("/rag")
@admin_required
def rag_pipeline():
    """Answer one question against one record, showing the vectors it used."""
    animals = get_animals_with_aliases()
    subjects = rag.build_subjects(
        animals, load_ecosystems(), load_protected_areas()
    )

    key = request.args.get("subject", "")
    kind, record = _pipeline_record(key)
    if not record and subjects:
        key = subjects[0].key
        kind, record = _pipeline_record(key)
    record_name = (
        (record or {}).get("name_my")
        or (record or {}).get("name_mm")
        or (record or {}).get("name")
        or ""
    )

    question = request.args.get("q", "").strip()[:4000]
    answer = None
    embed_status = embeddings.status()
    vectors = []
    query_vector = None
    trace = handover_url = None
    if question and record:
        passages = rag.record_passages(kind, record)
        try:
            question_vector, passage_vectors = embeddings.retrieval_vectors(
                question,
                passages,
                allow_online=embeddings.online_enabled(),
                cache_question=True,
            )
        except embeddings.EmbeddingError as exc:
            flash(f"OpenAI query embedding မရပါ — {exc}", "error")
            question_vector, passage_vectors = embeddings.retrieval_vectors(
                question, passages
            )
        trace = rag.trace(
            question,
            kind,
            record,
            subjects,
            key,
            question_vector=question_vector,
            passage_vectors=passage_vectors,
            semantic_threshold=Config.EMBED_THRESHOLD,
        )
        vectors = _vector_rows(
            question_vector, passages, passage_vectors, trace["selected"]
        )
        if question_vector:
            query_vector = {
                "preview": question_vector[:PREVIEW_DIMS],
                "rest": max(len(question_vector) - PREVIEW_DIMS, 0),
                "dims": len(question_vector),
            }
        if trace["subject"]:
            handover_url = _subject_page_url(trace["subject"])
        answer = _final_answer(kind, record, record_name, question, trace)

    return render_template(
        "admin/rag_pipeline.html",
        subjects=subjects,
        subject_key=key,
        question=question,
        trace=trace,
        vectors=vectors,
        query_vector=query_vector,
        handover_url=handover_url,
        embed=embed_status,
        answer=answer,
        csrf_token=csrf_token(),
    )


@bp.route("/rag/answer", methods=["POST"])
@admin_required
def rag_answer():
    """Generate one answer for the console, without touching chat history.

    This is a bench: it runs the same retrieval and assembles the same request
    a member's chat would, then streams the reply back in the same NDJSON
    shape.  It saves nothing and reads no history, and it answers with the
    configured chat model — the same one the member's chat uses, so a reply
    here is the reply they would get.
    """
    from app import build_animal_prompt, build_content_prompt, build_chat_messages

    require_csrf()
    key = request.form.get("subject", "")
    question = request.form.get("q", "").strip()[:4000]
    model = Config.DEEPSEEK_MODEL
    kind, record = _pipeline_record(key)
    if not record or not question:
        return jsonify({"error": "A record and a question are required"}), 400

    passages = rag.record_passages(kind, record)
    try:
        question_vector, passage_vectors = embeddings.retrieval_vectors(
            question,
            passages,
            allow_online=embeddings.online_enabled(),
            cache_question=True,
        )
    except embeddings.EmbeddingError:
        question_vector, passage_vectors = embeddings.retrieval_vectors(
            question, passages
        )
    selected, _ = rag.retrieve(
        question,
        passages,
        question_vector=question_vector,
        passage_vectors=passage_vectors,
        semantic_threshold=Config.EMBED_THRESHOLD,
    )
    if not selected:
        return jsonify({"error": "Nothing was retrieved, so no model is called"}), 400

    prompt = (
        build_animal_prompt(record, selected)
        if kind == "animal"
        else build_content_prompt(kind, record, selected)
    )
    # No history: a bench run has to be repeatable, and an administrator's own
    # conversation must not colour what the next question retrieves.
    messages = build_chat_messages(prompt, [], question)

    def generate():
        started = time.monotonic()
        first_token = None
        try:
            with llm.open_stream(messages, model=model, read_timeout=300) as response:
                full = ""
                for delta in llm.iter_deltas(response):
                    if first_token is None:
                        first_token = time.monotonic() - started
                    full += delta
                    yield json.dumps(
                        {"content": delta, "done": False}, ensure_ascii=False
                    ) + "\n"
                yield json.dumps(
                    {
                        "content": "",
                        "done": True,
                        "model": model,
                        "characters": len(full),
                        "first_token": round(first_token or 0, 2),
                        "total": round(time.monotonic() - started, 2),
                        "passages": [item.label for item in selected],
                    },
                    ensure_ascii=False,
                ) + "\n"
        except llm.LLMError as error:
            yield json.dumps(
                {"error": f"DeepSeek မှ အဖြေ မရပါ — {error}"}, ensure_ascii=False
            ) + "\n"

    return Response(
        stream_with_context(generate()), mimetype="application/x-ndjson"
    )


@bp.post("/rag/index")
@admin_required
def rag_index():
    """Build a complete OpenAI index for every current published record."""
    from app import embedding_catalog_records

    require_csrf()
    if not embeddings.online_enabled():
        flash(
            "OpenAI indexing မရနိုင်ပါ။ Admin process တွင် OPENAI_API_KEY "
            "သတ်မှတ်ထားကြောင်း စစ်ဆေးပါ။",
            "error",
        )
        return redirect(url_for("admin.rag_pipeline"))

    records = embedding_catalog_records()
    valid = []
    total_passages = total_new = 0
    try:
        for content_kind, record_key, record in records:
            result = embeddings.index_record(
                content_kind,
                record_key,
                rag.record_passages(content_kind, record),
            )
            valid.append((content_kind, record_key))
            total_passages += result["passages"]
            total_new += result["new_vectors"]
        embeddings.finish_full_index(valid)
    except embeddings.EmbeddingError as exc:
        flash(f"Full OpenAI index မပြီးဆုံးပါ — {exc}", "error")
        return redirect(url_for("admin.rag_pipeline"))

    flash(
        f"Full OpenAI index ပြီးပါပြီ — record {len(records)} ခု၊ "
        f"passage {total_passages} ခု၊ vector အသစ် {total_new} ခု။",
        "success",
    )
    return redirect(url_for("admin.rag_pipeline"))


@bp.app_errorhandler(403)
def forbidden(error):
    return render_template("admin/forbidden.html"), 403
