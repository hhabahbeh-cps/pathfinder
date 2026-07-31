import os
import math
import datetime
import requests
from typing import List, Dict, Any, Optional, Union
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="CPS Master Data, Spatial & Academic MCP Server")

# Official CPS API Endpoints
CURRENT_YEAR = datetime.date.today().year
PRIMARY_CPS_MAP_URL = f"https://dev.api.cps.edu/maps/cps/GeoJSON?mapname=School&year={CURRENT_YEAR}"
FALLBACK_SOCRATA_URL = "https://data.cityofchicago.org/resource/3dhs-m3w4.json"
PROGRESS_API_BASE = "https://dev.api.cps.edu/schooldataprogress"

# Selective Enrollment High School Historical Cutoffs (900-Point Scale)
SEHS_CUTOFFS = {
    "Walter Payton College Prep": {"Citywide": 885, "Tier1": 810, "Tier2": 869, "Tier3": 870, "Tier4": 888},
    "Northside College Prep": {"Citywide": 875, "Tier1": 795, "Tier2": 846, "Tier3": 860, "Tier4": 880},
    "Jones College Prep": {"Citywide": 865, "Tier1": 775, "Tier2": 853, "Tier3": 850, "Tier4": 870},
    "Whitney M. Young Magnet HS": {"Citywide": 870, "Tier1": 785, "Tier2": 842, "Tier3": 855, "Tier4": 875},
    "Lane Technical High School": {"Citywide": 840, "Tier1": 735, "Tier2": 816, "Tier3": 820, "Tier4": 855},
    "John Hancock College Prep": {"Citywide": 830, "Tier1": 710, "Tier2": 813, "Tier3": 815, "Tier4": 835},
    "Kenwood Academy High School": {"Citywide": 820, "Tier1": 700, "Tier2": 750, "Tier3": 800, "Tier4": 825},
    "Lindblom Math and Science Academy": {"Citywide": 810, "Tier1": 690, "Tier2": 749, "Tier3": 790, "Tier4": 815},
    "Gwendolyn Brooks College Prep": {"Citywide": 800, "Tier1": 680, "Tier2": 741, "Tier3": 780, "Tier4": 805},
    "Westinghouse High School": {"Citywide": 790, "Tier1": 670, "Tier2": 735, "Tier3": 770, "Tier4": 795},
    "King College Prep High School": {"Citywide": 750, "Tier1": 600, "Tier2": 610, "Tier3": 720, "Tier4": 760}
}

# Academic Center Historical Cutoffs (600-Point Scale)
ACADEMIC_CENTER_CUTOFFS = {
    "Whitney Young Academic Center": {"Citywide": 560, "Tier1": 520, "Tier2": 535, "Tier3": 550, "Tier4": 565},
    "Lane Tech Academic Center": {"Citywide": 530, "Tier1": 490, "Tier2": 510, "Tier3": 525, "Tier4": 540},
    "Kenwood Academic Center": {"Citywide": 480, "Tier1": 435, "Tier2": 455, "Tier3": 475, "Tier4": 490},
    "Lindblom Academic Center": {"Citywide": 470, "Tier1": 425, "Tier2": 445, "Tier3": 465, "Tier4": 480},
    "Taft Academic Center": {"Citywide": 465, "Tier1": 420, "Tier2": 440, "Tier3": 460, "Tier4": 475},
    "Brooks Academic Center": {"Citywide": 430, "Tier1": 390, "Tier2": 410, "Tier3": 425, "Tier4": 440},
    "Morgan Park Academic Center": {"Citywide": 420, "Tier1": 380, "Tier2": 400, "Tier3": 415, "Tier4": 430}
}

# ZIP Code to CPS Socioeconomic Tier Mapping
ZIP_TO_TIER_MAP = {
    "60621": 1, "60623": 1, "60624": 1, "60636": 1, "60644": 1, "60651": 1, "60609": 1,
    "60617": 2, "60619": 2, "60620": 2, "60628": 2, "60632": 2, "60639": 2, "60649": 2,
    "60618": 3, "60622": 3, "60625": 3, "60630": 3, "60631": 3, "60647": 3, "60656": 3,
    "60601": 4, "60602": 4, "60603": 4, "60604": 4, "60605": 4, "60611": 4, "60613": 4,
    "60614": 4, "60657": 4, "60615": 4
}

# Dynamic GeoJSON Cache
_GEO_CACHE: List[Dict[str, Any]] = []

def fetch_school_features() -> List[Dict[str, Any]]:
    global _GEO_CACHE
    if _GEO_CACHE:
        return _GEO_CACHE

    # Primary Attempt: Direct CPS Maps API
    try:
        resp = requests.get(PRIMARY_CPS_MAP_URL, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "features" in data and len(data["features"]) > 0:
                _GEO_CACHE = data["features"]
                return _GEO_CACHE
    except Exception as e:
        print(f"[WARN] Primary CPS API fetch failed: {e}")

    # Fallback Attempt: Socrata Open Data Portal
    try:
        resp = requests.get(f"{FALLBACK_SOCRATA_URL}?$limit=1000", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                _GEO_CACHE = data
                return _GEO_CACHE
    except Exception as e:
        print(f"[WARN] Fallback dataset fetch failed: {e}")

    return []

# ==========================================
# TOOL FUNCTIONS
# ==========================================

# 1. Academic Center Calculator (600 Points)
def calculate_academic_center_chances(
    reading_grade: str, math_grade: str, science_grade: str, social_studies_grade: str,
    academic_center_exam_score: int, user_tier: int
) -> Dict[str, Any]:
    grade_map = {"A": 75.0, "B": 50.0, "C": 25.0, "D": 0.0, "F": 0.0}
    grade_points = (
        grade_map.get(reading_grade.upper(), 0) + grade_map.get(math_grade.upper(), 0) +
        grade_map.get(science_grade.upper(), 0) + grade_map.get(social_studies_grade.upper(), 0)
    )
    exam_points = min(300, academic_center_exam_score)
    total_score = grade_points + exam_points
    tier_key = f"Tier{user_tier}" if 1 <= user_tier <= 4 else "Citywide"

    evals = []
    for program, cutoffs in ACADEMIC_CENTER_CUTOFFS.items():
        req_cutoff = cutoffs.get(tier_key, cutoffs["Citywide"])
        diff = total_score - req_cutoff
        likelihood = "High Probability" if diff >= 15 else ("Competitive / Target" if diff >= -10 else "Reach Program")
        evals.append({
            "program_name": program,
            "calculated_score": total_score,
            "tier_cutoff": req_cutoff,
            "score_delta": round(diff, 1),
            "admission_likelihood": likelihood,
            "guaranteed_high_school_continuation": True
        })

    return {
        "student_summary": {
            "scale": "600 Points Total",
            "grade_points_earned": grade_points,
            "exam_points_earned": exam_points,
            "total_calculated_score": total_score,
            "user_tier": user_tier
        },
        "program_evaluations": evals
    }

# 2. Selective Enrollment High School Calculator (900 Points)
def calculate_selective_enrollment_chances(
    reading_grade: str, math_grade: str, science_grade: str, social_studies_grade: str,
    hsat_math_score: int, hsat_reading_score: int, user_tier: int
) -> Dict[str, Any]:
    grade_map = {"A": 112.5, "B": 75.0, "C": 37.5, "D": 0.0, "F": 0.0}
    grade_points = (
        grade_map.get(reading_grade.upper(), 0) + grade_map.get(math_grade.upper(), 0) +
        grade_map.get(science_grade.upper(), 0) + grade_map.get(social_studies_grade.upper(), 0)
    )
    exam_points = min(450, hsat_math_score + hsat_reading_score)
    total_score = grade_points + exam_points
    tier_key = f"Tier{user_tier}" if 1 <= user_tier <= 4 else "Citywide"

    evals = []
    for school, cutoffs in SEHS_CUTOFFS.items():
        req_cutoff = cutoffs.get(tier_key, cutoffs["Citywide"])
        diff = total_score - req_cutoff
        likelihood = "High Probability" if diff >= 15 else ("Competitive / Target" if diff >= -10 else "Reach School")
        evals.append({
            "school_name": school,
            "calculated_score": total_score,
            "tier_cutoff": req_cutoff,
            "score_delta": round(diff, 1),
            "admission_likelihood": likelihood
        })

    return {
        "student_summary": {
            "scale": "900 Points Total",
            "grade_points_earned": grade_points,
            "exam_points_earned": exam_points,
            "total_calculated_score": total_score,
            "user_tier": user_tier
        },
        "evaluations": evals
    }

# 3. CPS Socioeconomic Tier Lookup
def lookup_cps_tier(zipcode: str, street_address: str = "") -> Dict[str, Any]:
    z = str(zipcode).strip()
    tier = ZIP_TO_TIER_MAP.get(z, 3)

    return {
        "address_evaluated": f"{street_address}, Chicago, IL {z}".strip(", "),
        "zipcode": z,
        "assigned_tier": tier,
        "tier_explanation": (
            f"Address in ZIP {z} falls under CPS Tier {tier}. "
            "CPS assigns Tiers 1-4 using Census data (income, education, homeownership, "
            "single-parent rates, ESL rates, and neighborhood school scores)."
        ),
        "admissions_impact": (
            f"In Selective Enrollment High School and Academic Center admissions, students "
            f"in Tier {tier} compete only against other Tier {tier} applicants for 70% of available program seats."
        )
    }

# 4. Simplified Walkability & Neighborhood Rating
def calculate_walkability_score(street_address: str, zipcode: str) -> Dict[str, Any]:
    z = str(zipcode).strip()
    dense_zips = ["60601", "60602", "60603", "60604", "60605", "60606", "60607", "60610", "60611", "60614", "60622", "60647", "60657"]
    is_dense = z in dense_zips

    return {
        "address": f"{street_address}, Chicago, IL {z}".strip(", "),
        "zipcode": z,
        "neighborhood_walkability_score": 98 if is_dense else 65,
        "transit_access_level": "Tier A - High CTA L & Rail Density" if is_dense else "Tier B - Moderate CTA Bus & Transit Service",
        "note": "CPS manages specific student transportation routes and Ventra passes directly through school offices upon enrollment."
    }

# 5. GeoJSON Database Query
def query_cps_database(query: str = "", zip_code: str = "", grade_cat: str = "") -> List[Dict[str, Any]]:
    features = fetch_school_features()
    results = []
    q = query.strip().lower()
    zip_str = str(zip_code).strip()
    cat_str = grade_cat.strip().upper()

    for item in features:
        props = item.get("properties", item) if isinstance(item, dict) else {}

        s_id = str(props.get("SchoolID") or props.get("school_id") or props.get("School_ID") or "").lower()
        name = str(props.get("SchoolName") or props.get("short_name") or props.get("Short_Name") or props.get("Name") or "").lower()
        addr = str(props.get("Address") or props.get("address") or props.get("StreetAddress") or "").lower()
        s_zip = str(props.get("Zip") or props.get("zip") or props.get("ZIP") or "").strip()
        s_cat = str(props.get("GradeCat") or props.get("primary_category") or props.get("Grade_Cat") or "").upper()

        match_query = not q or (q in s_id or q in name or q in addr)
        match_zip = not zip_str or (zip_str == s_zip)
        match_cat = not cat_str or (cat_str in s_cat or (cat_str == "HS" and "HIGH" in s_cat))

        if match_query and match_zip and match_cat:
            results.append({
                "school_id": props.get("SchoolID") or props.get("school_id") or props.get("School_ID"),
                "name": props.get("SchoolName") or props.get("short_name") or props.get("Short_Name") or props.get("Name"),
                "address": props.get("Address") or props.get("address") or props.get("StreetAddress"),
                "zip": props.get("Zip") or props.get("zip") or props.get("ZIP"),
                "category": props.get("GradeCat") or props.get("primary_category") or props.get("Grade_Cat")
            })

    return results[:10]

# 6. School Comparison Grid
def generate_comparison_grid(school_ids: List[str]) -> Dict[str, Any]:
    features = fetch_school_features()
    targets = [str(sid).strip().lower() for sid in school_ids[:5]]

    compared = []
    for item in features:
        props = item.get("properties", item) if isinstance(item, dict) else {}
        s_id = str(props.get("SchoolID") or props.get("school_id") or props.get("School_ID") or "").strip().lower()
        s_name = str(props.get("SchoolName") or props.get("short_name") or props.get("Short_Name") or props.get("Name") or "").strip().lower()

        if any(t in s_id or t in s_name for t in targets):
            compared.append({
                "school_id": props.get("SchoolID") or props.get("school_id") or props.get("School_ID"),
                "name": props.get("SchoolName") or props.get("short_name") or props.get("Short_Name") or props.get("Name"),
                "address": props.get("Address") or props.get("address") or props.get("StreetAddress"),
                "zip": props.get("Zip") or props.get("zip") or props.get("ZIP"),
                "governance": props.get("Governance") or props.get("governance"),
                "category": props.get("GradeCat") or props.get("primary_category") or props.get("Grade_Cat")
            })

    return {"count": len(compared), "grid_data": compared}

# 7. Behavior & Discipline Data Tool
def get_school_behavior_metrics(school_code: Optional[Union[int, str]] = None) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    try:
        url = f"{PROGRESS_API_BASE}/BehaviorSchoolLevel/schools/{school_code}" if school_code else f"{PROGRESS_API_BASE}/BehaviorSchoolLevel/schools"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not school_code and isinstance(data, list):
            return {"total_records": len(data), "sample_schools": data[:5]}
        return data
    except requests.RequestException as e:
        return {"error": f"Failed to fetch behavior metrics: {str(e)}"}

# ==========================================
# MCP ROUTER / JSON-RPC HANDLER
# ==========================================

@app.get("/")
@app.get("/mcp")
async def health_check():
    return {
        "status": "online",
        "server": "CPS Selective Enrollment & Academic Centers MCP",
        "message": "Send POST requests with JSON-RPC payload to /mcp to execute tools."
    }

@app.post("/mcp")
async def handle_mcp(request: Request):
    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "CPS-Master-Data-Server", "version": "1.0"}
            }
        })

    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "calculate_academic_center_chances",
                        "description": "Calculates 600-point total score for 7th/8th grade Academic Centers and evaluates likelihood against historical tier cutoffs.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "reading_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "math_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "science_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "social_studies_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "academic_center_exam_score": {"type": "integer", "description": "Score out of 300 on Academic Center Admissions Exam"},
                                "user_tier": {"type": "integer", "description": "CPS Socioeconomic Tier (1-4)"}
                            },
                            "required": ["reading_grade", "math_grade", "science_grade", "social_studies_grade", "academic_center_exam_score", "user_tier"]
                        }
                    },
                    {
                        "name": "calculate_selective_enrollment_chances",
                        "description": "Calculates 900-point total score for 9th grade Selective Enrollment High Schools and evaluates likelihood against historical tier cutoffs.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "reading_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "math_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "science_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "social_studies_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                                "hsat_math_score": {"type": "integer"},
                                "hsat_reading_score": {"type": "integer"},
                                "user_tier": {"type": "integer"}
                            },
                            "required": ["reading_grade", "math_grade", "science_grade", "social_studies_grade", "hsat_math_score", "hsat_reading_score", "user_tier"]
                        }
                    },
                    {
                        "name": "lookup_cps_tier",
                        "description": "Returns the CPS Socioeconomic Tier (1 to 4) for a Chicago address or ZIP code.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "zipcode": {"type": "string", "description": "5-digit Chicago ZIP code"},
                                "street_address": {"type": "string", "description": "Optional street address"}
                            },
                            "required": ["zipcode"]
                        }
                    },
                    {
                        "name": "calculate_walkability_score",
                        "description": "Evaluates neighborhood walkability rating and CTA transit density tier.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "street_address": {"type": "string"},
                                "zipcode": {"type": "string"}
                            },
                            "required": ["street_address", "zipcode"]
                        }
                    },
                    {
                        "name": "query_cps_database",
                        "description": "Searches GeoJSON CPS dataset by keyword, zip code, or grade category.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "zip_code": {"type": "string"},
                                "grade_cat": {"type": "string"}
                            }
                        }
                    },
                    {
                        "name": "generate_comparison_grid",
                        "description": "Generates a side-by-side comparison payload for up to 5 school IDs.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "school_ids": {"type": "array", "items": {"type": "string"}}
                            },
                            "required": ["school_ids"]
                        }
                    },
                    {
                        "name": "get_school_behavior_metrics",
                        "description": "Fetches discipline, misconduct, ISS/OSS, and police notifications by school code.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "school_code": {"type": ["integer", "string"]}
                            }
                        }
                    }
                ]
            }
        })

    elif method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "calculate_academic_center_chances":
            res = calculate_academic_center_chances(
                args.get("reading_grade"), args.get("math_grade"),
                args.get("science_grade"), args.get("social_studies_grade"),
                args.get("academic_center_exam_score"), args.get("user_tier")
            )
        elif tool_name == "calculate_selective_enrollment_chances":
            res = calculate_selective_enrollment_chances(
                args.get("reading_grade"), args.get("math_grade"),
                args.get("science_grade"), args.get("social_studies_grade"),
                args.get("hsat_math_score"), args.get("hsat_reading_score"), args.get("user_tier")
            )
        elif tool_name == "lookup_cps_tier":
            res = lookup_cps_tier(args.get("zipcode"), args.get("street_address", ""))
        elif tool_name == "calculate_walkability_score":
            res = calculate_walkability_score(args.get("street_address"), args.get("zipcode"))
        elif tool_name == "query_cps_database":
            res = query_cps_database(args.get("query", ""), args.get("zip_code", ""), args.get("grade_cat", ""))
        elif tool_name == "generate_comparison_grid":
            res = generate_comparison_grid(args.get("school_ids", []))
        elif tool_name == "get_school_behavior_metrics":
            res = get_school_behavior_metrics(args.get("school_code"))
        else:
            res = {"error": f"Unknown tool: {tool_name}"}

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": str(res)}]
            }
        })

    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})

if __name__ == "__main__":
    import uvicorn
    # Render sets $PORT dynamically; fallback to 10000 only for local dev
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

