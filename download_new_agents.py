"""
download_new_agents.py  —  Download PDFs for ISA, CMISA, Ministry of Justice, Tax Authority
Run: python download_new_agents.py
"""
import time
import requests
from pathlib import Path

BASE = Path(__file__).parent
KB   = BASE / "knowledge_base"

PDFS = {
    "securities_authority": [
        ("https://www.new.isa.gov.il/en/images/Fittings/isa-be/asset_library_pic/al_lobby/al_lobby-649135bbde875/ANNUALREPORT2023.pdf",       "isa_annual_report_2023_en.pdf"),
        ("https://www.isa.gov.il/sites/ISAEng/1489/1512/Documents/ISA_AnnualReport_ENG_2020.pdf",                                              "isa_annual_report_2020_en.pdf"),
        ("https://www.new.isa.gov.il/en/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-64fee64cb474c/13052021.pdf",                   "isa_csr_esg_disclosure_guidance_2021_en.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/Foreign_Underwriters_Guide.pdf",                                    "isa_guide_foreign_underwriters_en.pdf"),
        ("https://www.new.isa.gov.il/en/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-64805b1867e84/IsaFile_0102151.pdf",            "isa_securities_law_5728_1968_en.pdf"),
        ("https://www.new.isa.gov.il/en/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-64805b1867e84/2652015_2.pdf",                  "isa_securities_regulations_foreign_issuers_en.pdf"),
        ("https://www.isa.gov.il/sites/ISAEng/1489/1512/Documents/ISA_Report__2013.pdf",                                                       "isa_annual_report_2013_en.pdf"),
        ("https://www.isa.gov.il/sites/ISAEng/1489/1512/Documents/24082016_1.pdf",                                                             "isa_annual_report_2016_en.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637b90c7be39b/AnnualReport2022.pdf",              "isa_annual_report_2022_he.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637b90c7be39b/ANNUAL_REPORT_2021.pdf",            "isa_annual_report_2021_he.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-63b3dc4fa5dd2/AIreport.pdf",                      "isa_ai_financial_sector_report_he.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-6280ee7d64354/brokers2024.pdf",                   "isa_broker_trust_account_audit_2024_he.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-6280ee7d64354/crowdfunding.pdf",                  "isa_crowdfunding_audit_2023_he.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637f2c2bb1c37/report_2024.pdf",                   "isa_annual_report_2024_he.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637f2c2bb1c37/FinancialReport2022-M.pdf",         "isa_financial_report_2022_he.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-65d5b849b3af3/Modification_TradingDays.pdf",      "isa_guide_trading_days_en.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_arenainternational_asset_library/arenaInternational_pdf_pages-63184b1778391/IsaFile_5617.pdf", "isa_international_affairs.pdf"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-628ccfb552dac/MoUbtwFSCISA.pdf",                  "isa_mou_fsc_israel_en.pdf"),
    ],
    "capital_markets_authority": [
        ("https://www.gov.il/BlobFolder/reports/report_0004/he/CMISA_AnnualReport2022_Ch2.pdf",                                                "cmisa_annual_report_2022_ch2_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/report_0004/he/CMISA_AnnualReport2022_Ch5.pdf",                                                "cmisa_annual_report_2022_ch5_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/report_0004/he/CMISA_AnnualReport2022_Ch7.pdf",                                                "cmisa_annual_report_2022_ch7_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/report_0004/he/CMISA_AnnualReport2022_Ch1.pdf",                                                "cmisa_annual_report_2022_ch1_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/report_0004/he/CMISA_AnnualReport2022_Ch3.pdf",                                                "cmisa_annual_report_2022_ch3_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/report_0004/he/CMISA_AnnualReport2022_Ch4.pdf",                                                "cmisa_annual_report_2022_ch4_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/report_0004/he/CMISA_AnnualReport2022_Ch6.pdf",                                                "cmisa_annual_report_2022_ch6_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/1_annual_report_2021/he/CMISA_AnnualReport_Chapter2.pdf",                                      "cmisa_annual_report_2021_ch2_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/1_annual_report_2021/he/CMISA_AnnualReport_Chapter3.pdf",                                      "cmisa_annual_report_2021_ch3_he.pdf"),
        ("https://www.gov.il/BlobFolder/reports/1_annual_report_2021/he/CMISA_AnnualReport_Chapter4.pdf",                                      "cmisa_annual_report_2021_ch4_he.pdf"),
        ("https://www.gov.il/BlobFolder/policy/regulation_cmisa_11/he/04_10_2024_pdf.pdf",                                                     "cmisa_ai_financial_sector_policy_2024_he.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2024/The-cost-of-living/EN/2024-The-cost-of-living-104-Hon-Taktzir-EN.pdf", "state_comptroller_2024_cmisa_cost_of_living_en.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2022/2022.11/EN/2022.11-307-Pension-EN.pdf",                           "state_comptroller_2022_cmisa_pension_en.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2020/71A/EN/2020-71A-202-Gimlaot-Taktzir-EN.pdf",                      "state_comptroller_2020_cmisa_pension_management_en.pdf"),
    ],
    "ministry_of_justice": [
        ("https://www.gov.il/BlobFolder/reports/new-annual-reports/en/annual-reports_eng_main-annual-report-2020-eng.pdf",  "ilpo_annual_report_2020_en.pdf"),
        ("https://www.gov.il/BlobFolder/reports/new-annual-reports/en/annual-reports_eng_main-annual-report-2019-eng.pdf",  "ilpo_annual_report_2019_en.pdf"),
        ("https://www.gov.il/BlobFolder/reports/new-annual-reports/en/annual-reports_eng_main-annual-report-2018-eng.pdf",  "ilpo_annual_report_2018_en.pdf"),
        ("https://www.gov.il/BlobFolder/reports/new-annual-reports/en/annual-reports_eng_main-annual-report-2016-eng.pdf",  "ilpo_annual_report_2016_en.pdf"),
        ("https://www.gov.il/BlobFolder/reports/new-annual-reports/en/annual-reports_eng_main-annual-report-2021-eng.pdf",  "ilpo_annual_report_2021_en.pdf"),
        ("https://www.gov.il/BlobFolder/reports/new-annual-reports/en/annual-reports_eng_main-annual-report-2022-eng.pdf",  "ilpo_annual_report_2022_en.pdf"),
        ("https://www.justice.gov.il/Units/RashamHaptentim/about/Documents/ILPO_en_2018.pdf",                               "ilpo_annual_report_2018_alt_en.pdf"),
        ("https://www.justice.gov.il/Units/RashamHaptentim/Documents/ILPO_Annual_Report_2015.pdf",                          "ilpo_annual_report_2015_en.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2023/2023.5-Cyber/2023.5-Cyber-Abstracts-EN.pdf",   "state_comptroller_2023_cyber_en.pdf"),
    ],
    "tax_authority": [
        ("https://www.gov.il/BlobFolder/reports/tax-professionaldivision/he/IncomeTax_IncomeTaxRepresentInfo_Professionaldivision2019.pdf", "ita_professional_division_2019_he.pdf"),
        ("https://secapp.taxes.gov.il/OpenApiUserGuide/OpenApiUserGuide_EN.pdf",                                                            "ita_open_api_guide_en.pdf"),
        ("https://taxes.gov.il/English/customs/PersonalImport/Documents/CustomsImmigrantandForeignresident.pdf",                            "ita_customs_guide_immigrants_en.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2022/2022.11/2022.11-203-Tax.pdf",                                  "state_comptroller_2022_ita_audit_he.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2022/2022.11/2022.11-202-Tax-Public.pdf",                           "state_comptroller_2022_ita_public_service_he.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2022/2022.11/2022.11-Abstracts-EN.pdf",                             "state_comptroller_2022_abstracts_en.pdf"),
        ("https://www.oecd.org/content/dam/oecd/en/topics/policy-sub-issues/global-tax-revenues/revenue-statistics-israel.pdf",             "oecd_revenue_statistics_israel_2024_en.pdf"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2025/2025-10/EN/2025.10-201-Nadlan-Taktzir-EN.pdf",                 "state_comptroller_2025_ita_real_estate_en.pdf"),
    ],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def download(url, dest):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        if r.status_code == 200 and len(r.content) > 5000:
            dest.write_bytes(r.content)
            return True, len(r.content)
        return False, r.status_code
    except Exception as e:
        return False, str(e)

total_ok = 0
total_fail = 0

for org, files in PDFS.items():
    out_dir = KB / org
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"  {org}  ({len(files)} files)")
    print(f"{'='*60}")
    ok = fail = 0
    for url, fname in files:
        dest = out_dir / fname
        if dest.exists() and dest.stat().st_size > 5000:
            print(f"  [skip]  {fname}")
            ok += 1; total_ok += 1
            continue
        print(f"  Downloading {fname} ...", end="", flush=True)
        success, info = download(url, dest)
        if success:
            print(f" OK ({info:,} bytes)")
            ok += 1; total_ok += 1
        else:
            print(f" FAILED ({info})")
            fail += 1; total_fail += 1
        time.sleep(0.4)
    print(f"  -> {ok} OK, {fail} failed")

print(f"\n{'='*60}")
print(f"  TOTAL: {total_ok} downloaded, {total_fail} failed")
print("\n  Next step: run ingest + export")
print("  python ingest.py --org securities_authority")
print("  python ingest.py --org capital_markets_authority")
print("  python ingest.py --org ministry_of_justice")
print("  python ingest.py --org tax_authority")
print("  python export_kb.py")
