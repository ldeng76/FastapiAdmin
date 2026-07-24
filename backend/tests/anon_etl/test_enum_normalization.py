from app.plugin.module_medical.hospital import enum_normalization as n


def test_normalize_all_enum_values(monkeypatch):
    monkeypatch.setattr(n, "_SEX_MAP_CACHE", {"男": "1"})
    monkeypatch.setattr(n, "_ETHNICITY_MAP_CACHE", {"汉族": "01"})
    monkeypatch.setattr(n, "_SMOKING_MAP_CACHE", {"从不": "1"})
    monkeypatch.setattr(n, "_ABO_MAP_CACHE", {"a": "1"})
    monkeypatch.setattr(n, "_RH_MAP_CACHE", {"阳性": "2"})
    assert n.normalize_sex("男") == "1"
    assert n.normalize_ethnicity("汉族") == "01"
    assert n.normalize_smoking_status("从不") == "1"
    assert n.normalize_abo_blood_type("A") == "1"
    assert n.normalize_rh_blood_type("阳性") == "2"


def test_empty_and_unknown_are_none_except_sex(monkeypatch):
    for name in ("_ETHNICITY_MAP_CACHE", "_SMOKING_MAP_CACHE", "_ABO_MAP_CACHE", "_RH_MAP_CACHE"):
        monkeypatch.setattr(n, name, {})
    assert n.normalize_ethnicity(None) is None
    assert n.normalize_smoking_status("unknown") is None
    assert n.normalize_abo_blood_type("A") is None
    assert n.normalize_rh_blood_type("") is None
