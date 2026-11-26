"""S2: unseen labels, value profiling, cross-script keys and weak-evidence linkage (synthetic)."""
from __future__ import annotations

import pytest

from anamika.detect import columns as C
from anamika.link.cluster import Evidence, Linker
from anamika.translit.keys import first_key, name_key, place_key


# ------------------------------------------------------------------ unseen headers

@pytest.mark.parametrize("header,role", [
    ("Hospital No", C.MRN), ("pt_id", C.MRN), ("hosp_reg_no", C.MRN), ("IP No.", C.MRN),
    ("Case Ref", C.MRN), ("mob_no", C.PHONE), ("call_back_no", C.PHONE), ("Cell", C.PHONE),
    ("Birth Dt", C.DOB), ("Janam Taarikh", C.DOB), ("Mareez", C.PATIENT_NAME), ("Aayu", C.AGE),
    ("Gram/Mohalla", C.VILLAGE), ("Niwas", C.ADDRESS), ("Abhibhavak", C.RELATIVE_NAME),
])
def test_unseen_header_variants(header: str, role: str) -> None:
    assert C.classify_label(header) == role


@pytest.mark.parametrize("header", ["bill_no", "sample_id", "test", "result", "unit"])
def test_non_identifier_headers_stay_unclassified(header: str) -> None:
    assert C.classify_label(header) not in (C.MRN, C.PHONE, C.PATIENT_NAME)


def common(word: str) -> bool:
    return word.casefold() in {"fever", "dengue", "positive", "platelets", "medicine", "general"}


def test_name_column_found_by_values_alone() -> None:
    vals = ["Zorawar Pundir", "Bhavika Tandel", "Ojaswini Rathore", "रुक्मिणी चौहान", "Fatehjit Sodhi"]
    assert C.profile_people_places(vals, common) == C.PERSON_NAME


def test_relative_column_found_by_values_alone() -> None:
    vals = ["S/O Kesar Pundir", "W/O Tejpal Gurjar", "D/O Ilavarasan Nair"]
    assert C.profile_people_places(vals, common) == C.RELATIVE_NAME


def test_address_column_found_by_values_alone() -> None:
    vals = ["H.No. 12, Mohalla Qila, Tehsil Lalganj", "House 4, near Pani Tanki, Distt. Unnao",
            "Ward 9, Gali 3, Tehsil Kadipur"]
    assert C.profile_people_places(vals, common) == C.ADDRESS


@pytest.mark.parametrize("vals", [["Dengue", "Typhoid", "Dengue", "Malaria"],
                                  ["Medicine", "Medicine", "General", "Medicine"],
                                  ["fever x 3 days", "cough", "pain abdomen"]])
def test_clinical_columns_are_not_names(vals: list[str]) -> None:
    assert C.profile_people_places(vals, lambda w: True) is None


# ------------------------------------------------------------------ cross-script keys

@pytest.mark.parametrize("latin,deva", [("Shahid", "शाहिद"), ("Mohd. Shahid", "मोहम्मद शाहिद"),
                                        ("Sunita Patel", "सुनीता पटेल"), ("Rajesh Yadav", "राजेश यादव"),
                                        ("Pooja", "पूजा"), ("Vikram Singh", "विक्रम सिंह")])
def test_name_keys_match_across_scripts(latin: str, deva: str) -> None:
    assert name_key(latin) == name_key(deva) is not None


def test_place_and_first_keys() -> None:
    assert place_key("Durgamau Kalan") == place_key("दुर्गामऊ कलां")
    assert first_key("Md. Shahid Ansari") == first_key("शाहिद")
    assert name_key("Kumar Devi") is None


def test_different_names_have_different_keys() -> None:
    assert name_key("Sumit") != name_key("Sunita")


# ------------------------------------------------------------------ weak-evidence linkage

def ev(rid: str, *keys: str, **kw) -> Evidence:
    e = Evidence(rid, set(keys))
    for k, v in kw.items():
        if k in ("age", "dob", "gender", "aadhaar"):
            e.attr(k, v)
        else:
            setattr(e, k, v)
    return e


def test_hindi_record_links_by_name_village_and_age() -> None:
    lk = Linker()
    lk.add(ev("reg", "mrn:JJH-1", pkey=name_key("Sunita Patel"), village=place_key("Durgamau Kalan"), age="47"))
    lk.add(ev("rx", pkey=name_key("सुनीता पटेल"), village=place_key("दुर्गामऊ कलां"), age="47"))
    res = lk.solve()
    assert res["reg"] == res["rx"] is not None


def test_name_village_with_incompatible_age_does_not_link() -> None:
    lk = Linker()
    lk.add(ev("mother", "mrn:A", pkey=name_key("Sunita Patel"), village=place_key("Rampura"), age="62"))
    lk.add(ev("daughter", pkey=name_key("Sunita Patel"), village=place_key("Rampura"), age="24"))
    res = lk.solve()
    assert res["mother"] != res["daughter"]


def test_strong_id_merges_ignore_age_noise() -> None:
    lk = Linker()
    lk.add(ev("a", "mrn:A", age="47"))
    lk.add(ev("b", "mrn:A", age="52"))
    res = lk.solve()
    assert res["a"] == res["b"]


def test_fragment_attaches_only_when_unambiguous() -> None:
    lk = Linker()
    lk.add(ev("reg", "mrn:A", pfirst=first_key("Meera Verma"), rfirst=first_key("Rajan Verma")))
    lk.add(ev("opd", "mrn:A"))
    lk.add(ev("note", pfirst=first_key("Meera"), rfirst=first_key("Rajan")))
    res = lk.solve()
    assert res["note"] == res["reg"] is not None


def test_fragment_with_two_candidate_patients_stays_unlinked() -> None:
    lk = Linker()
    lk.add(ev("reg1", "mrn:A", pfirst=first_key("Meera Verma"), rfirst=first_key("Rajan Verma")))
    lk.add(ev("x1", "mrn:A"))
    lk.add(ev("reg2", "mrn:B", pfirst=first_key("Meera Rao"), rfirst=first_key("Rajan Rao")))
    lk.add(ev("x2", "mrn:B"))
    lk.add(ev("note", pfirst=first_key("Meera"), rfirst=first_key("Rajan")))
    res = lk.solve()
    assert res["note"] not in (res["reg1"], res["reg2"])
