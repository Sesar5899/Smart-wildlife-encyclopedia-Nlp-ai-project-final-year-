# Template execution contract

## Reference

- Retained DOCX: `/Users/myominko/Downloads/Final Body UniSync.docx`
- SHA-256: `5e581809aeecd3fe16c5dc8505eebbbdd9fc3abe38b14e451f2ab27f27c10ea6`
- Render: `/private/tmp/wildlife-doc/template-render` (57 pages)
- Style evidence: `/private/tmp/wildlife-doc/evidence/template-style-evidence.json`
- Structural evidence: `/private/tmp/wildlife-doc/evidence/reference-structure.txt`
- Page contact sheets: `/private/tmp/wildlife-doc/contact-sheets`
- Sections: one continuous section; each chapter after Chapter 1 starts on a manual new page.

## Page system

- ISO A4 portrait: 8.26875 × 11.69375 inches.
- Margins: 1 inch on all sides.
- Header distance: 0.5 inch; no visible header content.
- Footer distance: 0.5 inch; centered Arabic page number, continuous from page 1.
- One column; no odd/even or special first-page header/footer.
- All normal paragraphs use 1.5 line spacing. Figure captions and selected dense figure paragraphs use single spacing.

## Typography and paragraph roles

- Dominant family: Times New Roman.
- Body: 12 pt, justified, 1.5 lines, 0.5-inch first-line indent, 6 pt after.
- Chapter label: Times New Roman 14 pt bold uppercase, centered, 1.5 lines, 6 pt before.
- Chapter title: Times New Roman 14 pt bold uppercase, centered, 1.5 lines.
- First-level numbered heading: Times New Roman 14 pt bold, left/justified, 6 pt before and after, no first-line indent.
- Second-level numbered heading: Times New Roman 12 pt bold, left, kept with the following paragraph.
- Bullets: Times New Roman 12 pt, justified, 1.5 lines, 0.5-inch left indent with 0.25-inch hanging indent, 3–6 pt after.
- Figure caption: Times New Roman 12 pt, centered, usually single-spaced and kept with the figure.
- Table caption: Times New Roman 12 pt, centered, 1.5 lines, 6 pt before and after.
- Data-dictionary table text: Times New Roman approximately 7–8 pt; header bold with pale blue-gray fill; thin gray/black borders.
- Code/command blocks are a task-specific exception: Consolas 8.5 pt, single-spaced, pale gray fill, thin gray border. This is required for legible installation commands and follows the reference's screenshot/terminal treatment.

## Lists and tables

- Use real Word bullet numbering; no fake bullet glyphs.
- Data dictionary tables have four columns in the fixed reference proportions: 1.1875, 0.9375, 1.8229, 2.3229 inches.
- Header labels: `Attribute Name`, `Data Type`, `Key Constraint`, `Description`.
- Table rows expand naturally; no fixed row heights. Repeat the first row when a table spans pages.
- Table and cell widths are explicit; table aligns with the text block.

## Components

- No cover page, abstract, table of contents, running header, colored chapter furniture, or decorative title page appears in the retained reference.
- Five chapters in this order: INTRODUCTION; BACKGROUND THEORY; SYSTEM ARCHITECTURE AND DESIGN; IMPLEMENTATION; CONCLUSION.
- Chapter 3 contains a system architecture figure, use-case figure, sequence figure, data dictionaries, and a database diagram.
- Chapter 4 alternates short implementation descriptions with centered desktop screenshots and captions, followed by an installation manual with commands.
- Chapter 5 ends with a numbered reference list.
- Figures are centered inline images, normally 5.77 inches wide; taller diagrams may use up to 6.26 inches within the 6.27-inch text area.

## Content flow and slot map

- Chapter 1: rewrite every UniSync paragraph for the wildlife project while preserving the section pattern `opening → 1.1 Motivation → 1.2 Aim and Objectives → 1.3 Advantage → 1.4 Summary`.
- Chapter 2: rewrite theory and proposed-method slots around biodiversity informatics, Myanmar NLP, search, RAG, embeddings, deterministic grounding, web security, and provenance; preserve the `2.1 / 2.2 / 2.3` ladder.
- Chapter 3: replace every architecture/design paragraph, figure, data dictionary, and database description with evidence from the current Flask/SQLite project. The supplied images are format references only because their UniSync and BeanDoctor entities are outside the requested project.
- Chapter 4: replace every implementation subsection and screenshot with desktop captures from the running wildlife application; use the eleven captured UI files under `report-assets/screenshots`. Replace the installation section with actual repository commands.
- Chapter 5: rewrite conclusion, limitations, future work, summary, and references for the wildlife project.
- Unsupported source slots for lectures, meetings, quizzes, cards, plans, exports, workers, audio, and React are removed; no unsupported feature is preserved merely to fill space.

## Package preservation

- Preserve the retained A4 section geometry and centered `PAGE` field behavior.
- Preserve source-derived paragraph rhythm, type hierarchy, bullet geometry, figure/caption pattern, and pale-blue data-dictionary treatment.
- The new report is a major content rewrite, so source body text, relationships to old UniSync images, and old tables are editable/removable.
- Preserve-only baseline parts: `_rels/.rels`, theme defaults, font table, web settings, and the semantic behavior of the footer page field. Python-docx may normalize package XML, so fidelity is judged structurally and visually rather than byte-for-byte for rewritten body parts.
- The retained reference itself must remain byte-for-byte unchanged.

## Fidelity gates

- A4 portrait, one-inch margins, Times New Roman, 1.5 line spacing, justified 12 pt body text, 14 pt chapter/section headings, centered footer page numbers.
- Five-chapter order and the same numbered section ladder.
- Desktop screenshots only; no mobile captures or mockups.
- Correct project title everywhere: `Smart Wildlife Encyclopedia using Retrieval-Augmented Generation & NLP`.
- No remaining `UniSync`, `BeanDoctor`, lecture/meeting, or unrelated schema text.
- Correct logical schema from `myanmar_wildlife/wildlife.db` and `db.py`.
- Every page rendered and visually inspected; no clipping, overlap, broken table, unreadable diagram, orphan caption, or unexplained blank page.
