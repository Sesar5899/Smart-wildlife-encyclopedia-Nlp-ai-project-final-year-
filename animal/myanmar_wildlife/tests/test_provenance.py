"""Field provenance must never turn an unrelated source into a citation."""

import json
import unittest
from types import SimpleNamespace

import provenance


class ProvenanceTests(unittest.TestCase):
    def test_backfill_only_unchanged_portal_values(self):
        url = "https://www.myanmarbiodiversity.org/species/Test_species"
        animal = {
            "source_url": url,
            "portal_data": json.dumps({
                "linked_name": "Test_species",
                "threats_to_survival_mm": "မူရင်း ခြိမ်းခြောက်မှု",
                "habitat_ecology_mm": "မူရင်း နေထိုင်ရာ",
            }),
            "threats_my": "မူရင်း ခြိမ်းခြောက်မှု",
            "habitat_my": "အယ်ဒီတာ ပြင်ထားသော နေထိုင်ရာ",
        }
        self.assertEqual(
            provenance.portal_field_sources(animal), {"threats_my": [url]}
        )

    def test_selected_passages_exclude_identity_and_unrelated_source(self):
        portal = "https://www.myanmarbiodiversity.org/species/Test_species"
        other = "https://example.org/habitat"
        animal = {
            "field_sources": {
                "name_my": [other], "threats_my": [portal], "habitat_my": [other]
            },
            "sources": [
                {"label": "Portal", "url": portal},
                {"label": "Other", "url": other},
            ],
        }
        passages = [
            SimpleNamespace(field="threats_my", identity=False),
            SimpleNamespace(field="name_my", identity=True),
        ]
        self.assertEqual(
            provenance.sources_for_passages(animal, passages),
            [{"label": "Portal", "url": portal}],
        )

    def test_protected_import_uses_each_fields_actual_provider(self):
        en = "https://en.wikipedia.org/wiki/Test"
        my = "https://my.wikipedia.org/wiki/Test"
        animal = {
            "source_record_id": "protected_mammal_2020_test",
            "scientific_name": "Test species",
            "portal_data": json.dumps({"protected_list_no": 1}),
            "source_urls": [{"url": en}, {"url": my}],
            "description_my": "မြန်မာ ဖော်ပြချက်",
            "threats_my": "English threats",
            "habitat_my": "ပြည်တွင်း တော",
        }
        cache = {
            "description": "မြန်မာ ဖော်ပြချက်",
            "description_language": "my",
            "threats": "English threats",
            "habitat": "ပြည်တွင်း တော",
            "en_url": en, "my_url": my,
        }
        self.assertEqual(provenance.imported_field_sources(animal, cache), {
            "description_my": [my],
            "threats_my": [en],
            "habitat_my": [my],
        })


if __name__ == "__main__":
    unittest.main()
