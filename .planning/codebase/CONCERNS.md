# Codebase Concerns

**Analysis Date:** 2026-04-17

## Tech Debt

**API Contract Drift (aoi_id vs. aoi + date mismatch):**
- Issue: Skeleton endpoints (`/detect`, `/forecast`, `/mission`) use query parameter `aoi_id` (string, defaulting to "mumbai"), but PRD §Appendix B §509–518 specifies contract requires `aoi` + `date` for `/detect`, `horizon` for `/forecast`, and POST body for `/mission`. Current implementation uses GET with `aoi_id` + `hours` parameters.
- Files: `backend/api/routes.py` (lines 11–28), `backend/main.py`
- Impact: Frontend integration will fail. Must reconcile parameter names and endpoint signatures before integration. Breaking change required to match PRD contract.
- Fix approach: Update `routes.py` to implement exact contract: `GET /detect?aoi=<id>&date=<YYYY-MM-DD>`, `GET /forecast?aoi=<id>&horizon=<hours>`, `POST /mission` with JSON body. Add validation for parameter formats.

**Missing /aois Endpoint:**
- Issue: PRD §Appendix B specifies `GET /aois` should list 4 demo AOIs, but no endpoint exists. Only `/detect`, `/forecast`, `/mission` are implemented.
- Files: `backend/api/routes.py`
- Impact: Frontend has no way to discover available AOIs. Dashboard bootstrap flow (PRD §7, step 1 "map centers on India's EEZ. Sidebar shows 4 demo AOIs as cards") cannot work.
- Fix approach: Add `GET /aois` endpoint returning list of AOI objects with metadata: `{id, name, bounds, last_updated, description}`. Pre-populate with 4 demo AOIs (Gulf of Mannar, Bay of Bengal mouth, Mumbai offshore, Arabian Sea gyre edge).

**Non-Idiomatic Error Handling:**
- Issue: `routes.py` line 23 returns `{"error": "Invalid forecast step..."}` dict instead of raising `HTTPException` with proper HTTP status code. This bypasses FastAPI's error handling middleware and returns 200 OK with error content.
- Files: `backend/api/routes.py` (line 23)
- Impact: Frontend cannot distinguish success from failure on status code. Error responses are inconsistent and non-RESTful. API clients expecting standard HTTP status codes will break.
- Fix approach: Replace `return {"error": "..."}` with `raise HTTPException(status_code=400, detail="Invalid forecast step. Allowed values are [24, 48, 72].")`. Apply pattern throughout all endpoints.

---

## Known Issues & Bugs

**CORS Configuration Not Hardened for Production:**
- Issue: `backend/main.py` line 16 sets `allow_origins=["*"]`, explicitly allowing all origins. Comment on line 13 states "Crucial to unblock the frontend React dev (allow all origins in dev mode)", but there is no conditional logic to tighten this for production deployment.
- Files: `backend/main.py` (lines 14–20)
- Impact: If the API is ever exposed beyond localhost (single-box demo is fine; cloud deployment is dangerous), malicious websites can make direct API calls on behalf of users. No CSRF protection.
- Workaround: Comment notes this is intentional for dev; deployment phase must add environment-based config.
- Recommendation: Before any cloud or shared deployment, add:
  ```python
  ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ENV") == "production" else ["*"]
  app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, ...)
  ```

**MARIDA Dataset Exposed in Git (4 GB not in .gitignore):**
- Issue: `MARIDA/` directory (4.5 GB) sits at project root and is NOT listed in `.gitignore` (line 25 excludes `data/` but not `MARIDA/`). The 4 GB dataset could accidentally be committed to remote if someone runs `git add .` without care.
- Files: `MARIDA/` (directory), `.gitignore` (missing exclusion)
- Impact: Accidental commit would bloat repo; risk of overwriting remote storage quota. Git operations would slow significantly.
- Fix approach: Add `MARIDA/` to `.gitignore` immediately. Verify it has not been committed yet: `git log --all --full-history -- MARIDA/`. For local development, mount or symlink the dataset from a shared location (Google Drive, Kaggle dataset, or local mount).

---

## Security Considerations

**Python Version Dependency Chain (Pre-Compiled Wheels):**
- Risk: Backend README §lines 8–11 warns: "DO NOT USE Python 3.13 or 3.14+ yet... Pre-built binary wheels are not yet stable for these alpha/beta versions... will throw a 'Failed to build shapely wheel' error." Also warns against 3.9 (too old for typing). Constrains to 3.10–3.12.
- Files: `backend/README.md` (lines 8–11), `backend/requirements.txt` (dependencies: shapely, geopandas)
- Current state: Test environment uses Python 3.11.3 (safe).
- Mitigation: Codify constraint in `setup.py` or `pyproject.toml`: `python_requires=">=3.10,<3.13"`. Document in `.python-version` (for `pyenv`) or `runtime.txt` (for Heroku).
- Recommendation: Add explicit version pinning to avoid team members or CI/CD using unsafe Python versions.

**Environment Variable Security (Secrets Not Visible):**
- Risk: `.env` file exists in `.gitignore` (line 5), which is correct — secrets are not committed. However, no `.env.example` or documentation of required env vars exists.
- Files: `.gitignore` (line 5), `.env` (assumed but not verified)
- Impact: New team members don't know what secrets are needed (Kaggle API keys? CMEMS credentials? Mapbox token?). OnBoarding friction.
- Recommendation: Create `.env.example` with placeholder values for all required secrets (after PRD review determines which integrations are enabled).

**No License File or Contributor Guide:**
- Risk: Repository has no LICENSE, CONTRIBUTING, or CODE_OF_CONDUCT file. Open-source or hackathon projects should clarify legal standing (especially if using MARIDA dataset, which is academic — may have data-use agreement restrictions).
- Files: Repository root (missing LICENSE, missing CONTRIBUTING.md)
- Impact: Unclear legal status. If code is shared with judges or published, copyright/attribution unclear. MARIDA usage might violate data-use terms if not properly cited.
- Recommendation: Add `LICENSE` (MIT or Apache 2.0 for hackathon). Add `CONTRIBUTING.md` with git workflow. Cite MARIDA dataset and all academic papers per PRD §Appendix A.

---

## Performance Bottlenecks

**Tight 24–48 Hour Hackathon Window (Scope Creep Risk):**
- Problem: PRD §16 explicitly marks "Overambitious scope creep" as HIGH likelihood / CRITICAL impact. The project is split across ML, backend, frontend, and physics — 4 independent tracks that all need to converge within 48 hours. Any delay in one track blocks the others.
- Files: PRD.md (§16, line 480), PRD.md (§13, execution timeline)
- Current state: Skeleton is minimal (96 LOC in services, 32 in routes); no ML code, no physics engine, no frontend, no tests. Everything remains to build.
- Risk detail: Each phase has hard dependency on prior phases:
  1. H0–H4: Must download datasets and create shared GeoJSON contract → any download failure cascades.
  2. H4–H16: ML training and physics validation → if model IoU < 0.3, must pivot to pretrained Segformer (loses hours). Physics validation on synthetic data → if bugs emerge, must debug under deadline.
  3. H16–H28: Integration of ML + physics into API → if data formats don't match, all 4 tracks must re-sync.
  4. H28–H40: Polish and demo features (animations, export) → typically where scope creep happens (new animations, new export formats).
  5. H40–H48: Rehearsal and fallback recording.
- Improvement path: Enforce "feature-freeze at H36" rule (PRD §13, line 414). Assign a "scope PM" role to block mid-phase feature requests. Prepopulate all 4 AOI responses by H28 (precompute static results) to avoid dynamic inference latency issues at demo time.

**Mock Data Does Not Match Real Feature Schema:**
- Problem: `backend/services/mock_data.py` returns hardcoded features with properties like `id`, `confidence`, `area_sq_meters`, `age_days`, `type`, but PRD §Appendix B §509–534 specifies detection feature schema with `conf_raw`, `conf_adj`, `fraction_plastic`, `area_m2`, `age_days_est`, `class`. These schemas are misaligned.
- Files: `backend/services/mock_data.py` (lines 30–36, 63, 86–90), PRD.md §Appendix B (lines 521–533)
- Impact: Frontend will expect `conf_adj` (adjusted confidence after biofouling decay) but mock returns `confidence` (single value). Property names differ (`area_sq_meters` vs `area_m2`, `type` vs `class`). Frontend parsing will fail or require defensive fallbacks.
- Fix approach: Update `mock_data.py` to match exact PRD schema. Use dual-confidence fields: `conf_raw` (base model output) and `conf_adj` (after decay). Compute `fraction_plastic`, `age_days_est` with plausible values.

---

## Fragile Areas

**Kaggle GPU Training Configuration Not Verified:**
- Files: (Assumed but not located) — PRD §13 (H4–H16) mentions "Train U-Net (iterate 2–3 times); log IoU, pick best" but no `kaggle.yml` or kernel-metadata files were found in repo.
- Why fragile: PRD context (problem statement intro) suggests MARIDA is from Kaggle. If team plan is to train on Kaggle (likely for free GPU), the kernel environment setup is critical. No configuration exists yet.
- Safe modification: Create `kaggle.json` (kernel metadata) with:
  - `enable_gpu: true` (PRD would specify if training should use GPU)
  - Framework: PyTorch (must be available in Kaggle kernel)
  - Imports: geopandas, rasterio, segmentation_models_pytorch (must be available)
- Test coverage: None yet — this is infrastructure. Should validate in H0 (Hours 0–4 "Foundation") before committing to training on Kaggle.

**Environment Data Prerequisites (CMEMS & ERA5 Account Setup) Not Done:**
- Issue: PRD §8.5 (trajectory engine, line 278) specifies "Pre-downloaded CMEMS + ERA5 NetCDFs". These datasets are public but require free account registration and API key management.
- Files: Not yet created — would be in `data/env/*.nc` (per PRD §14, line 439)
- Current state: No CMEMS or ERA5 downloads exist. No documentation of registration workflow.
- Safe modification: Pre-H4, one team member must:
  1. Register at CMEMS (Copernicus Marine): https://data.marine.copernicus.eu/ → download 7-day global surface currents (u, v) at 1/12° resolution.
  2. Register at CDS (Climate Data Store): https://cds.climate.copernicus.eu/ → download ERA5 10m winds (u10, v10) at 0.25° resolution for demo window.
  3. Clip spatial extent to AOI bounding boxes to reduce file size (per PRD §16, line 477 "Env NetCDFs too large" mitigation).
  4. Document download commands in `README.md`.
- Risk: If registration is not done early, H4–H16 physics validation cannot proceed → cascades to H16–H28 integration.

**Missing Unit Tests & Validation for Physics Module:**
- Files: No test files exist for `backend/physics/tracker.py` (not yet written)
- Why fragile: PRD §15 (verification plan, lines 447–450) specifies unit tests for physics: "synthetic eastward 0.5 m/s current field → particle displaces 43.2 km in 24h (±1%)". If this is not validated before H28 integration, trajectory bugs will emerge at demo time.
- Safe modification: When `backend/physics/tracker.py` is written, include a simple test function:
  ```python
  def test_lagrangian_displacement():
      # Uniform eastward current: 0.5 m/s
      u_field = np.ones((100, 100)) * 0.5
      v_field = np.zeros((100, 100))
      x0, y0 = 0, 0
      x_final, y_final = integrate_24h(x0, y0, u_field, v_field)
      expected_displacement_m = 0.5 * 24 * 3600  # 43.2 km
      assert abs(x_final - expected_displacement_m) < 0.01 * expected_displacement_m
  ```
- Priority: HIGH — must pass before H16 / before integration phase.

---

## Scaling Limits

**Dashboard Single-Box Deployment (No Multi-Instance Failover):**
- Current capacity: PRD §12 (line 371) explicitly states "Cloud deployment (AWS/GCP). Demo on laptop. One less thing to break." Single-instance FastAPI + React bundle running on demo laptop.
- Limit: If demo laptop crashes or loses power mid-presentation, entire system fails. No load balancing, no hot standby, no graceful degradation.
- Scaling path: For post-hackathon use (INCOIS integration, production), move to:
  1. Containerized FastAPI (Docker Compose on localhost now; Docker Swarm or K8s for production).
  2. Separate frontend assets (static S3 bucket or CDN).
  3. Persistent model serving (Ray Serve or TFServing if real inference becomes bottleneck).
  4. Database for caching inference results instead of re-computing on every request.

**Inference Latency Not Measured (5 sec Target from PRD Unknown):**
- Issue: PRD §11.1 (line 335) specifies inference latency target: "≤ 5 sec (single-tile dashboard response)". No latency testing is in place; mock endpoints return instantly. Real U-Net inference on 1024×1024 tile has no measured performance baseline.
- Files: No benchmarking code exists yet; will be measured in H16–H28 integration phase.
- Current state: Mock returns hardcoded data (~1 ms).
- Risk: If real inference takes 15+ seconds, time-slider scrubbing (PRD §7, step 4 "user drags 0 → 72h") will stall. May need to precompute and cache all 4 AOIs at H28–H40 phase (per PRD §14, line 406 "Populate dashboard for all 4 AOIs (pre-bake responses)").

---

## Dependencies at Risk

**No Testing Framework Installed:**
- Risk: `backend/requirements.txt` does not include pytest, unittest, or any testing library. PRD §15 requires unit tests for features.py, tracker.py, and model-level validation. No way to run tests.
- Files: `backend/requirements.txt` (lines 1–8) — missing `pytest>=7.0`
- Impact: Cannot automate verification of critical components (FDI computation, Lagrangian tracking, model IoU). Team will rely on manual/ad-hoc testing, increasing bug likelihood.
- Migration plan: Add `pytest==7.0.0` and `pytest-cov==4.1.0` to requirements.txt. Create `backend/tests/` directory. Write minimal tests for each module (at least one test per critical function).

**Dependency Version Pins Allow Breaking Changes:**
- Risk: `requirements.txt` pins exact versions (fastapi==0.110.0, uvicorn==0.29.0), which is good. However, geospatial dependencies (shapely, geopandas) are pinned without considering compatibility with newer PyTorch or numpy (not yet in requirements, but will be added for ML phase).
- Files: `backend/requirements.txt` (lines 7–8)
- Impact: When `pytorch` and `segmentation_models_pytorch` are added, version conflicts may emerge (e.g., shapely 2.0 requires different numpy than older PyTorch builds). Setup failures in H4–H16.
- Mitigation: Use `pip-tools` or `poetry` to lock all transitive dependencies before H4. Test full requirements.txt in CI or locally before committing.

---

## Missing Critical Features

**No Model Weights Distribution Plan:**
- Issue: PRD §13 (H4–H16) trains a U-Net model, but no plan exists for where to store/serve the trained weights (`.pth` file). Cannot be committed to git (too large).
- Files: Not yet created
- Blocks: H16–H28 integration cannot begin without model weights. H28–H40 demo cannot run without model weights.
- Plan: Store model weights in shared drive (Google Drive, Kaggle dataset, or GitHub Releases). Document download command in `README.md`. Or: pre-train offline, upload to `data/models/` (add to `.gitignore`), and include download script at clone time.

**No Satellite Tile Management System:**
- Issue: PRD §14 (line 438) specifies "4 demo Sentinel-2 L2A tiles" must be pre-staged in `data/staged/*.tif`, but no system for tile versioning, metadata, or refresh. If a tile is corrupted or outdated, no automated way to re-download.
- Files: `data/staged/` (does not exist yet)
- Impact: Demo fragility — if a single tile becomes unavailable, one of four AOIs fails.
- Plan: Create `data/README.md` with download commands for each tile + checksums (MD5/SHA256 for integrity). Version-tag each tile with acquisition date (S2 L2A has consistent naming: `S2A_MSIL2A_20260415T...`).

**No Biofouling Augmentation Implementation Exists:**
- Issue: PRD §8.4 (lines 250–254) specifies training-time augmentation: "for 40% of positive samples, multiply NIR and RedEdge bands by sampled factor ∈ [0.5, 1.0] simulating 0–60 day biofouling age." No code exists yet; critical for model robustness to realistic deployment (aging patches).
- Files: Not yet written — will be in `backend/ml/dataset.py`
- Impact: If augmentation is not implemented, model will fail on older patches with reduced NIR signal (biofouling effect). Detection sensitivity will drop over time in real deployment.
- Safe modification: When dataloader is written, add:
  ```python
  def augment_biofouling(sample, probability=0.4):
      if random.random() < probability:
          age_factor = random.uniform(0.5, 1.0)
          sample['B8'] *= age_factor  # NIR
          sample['B6'] *= age_factor  # RedEdge2
      return sample
  ```

---

## Test Coverage Gaps

**No Integration Tests for API Contract:**
- Untested area: API endpoints do not have integration tests. Mock endpoints return hardcoded data; no validation that schema changes will be caught.
- Files: `backend/api/routes.py` (entire module), `backend/main.py` (CORS config)
- Risk: When real ML/physics modules are integrated, API schema will drift silently. Frontend will fail at demo time with cryptic JSON parsing errors.
- Priority: HIGH — should write tests before integration (H16–H28). At minimum:
  ```python
  def test_detect_endpoint_schema():
      response = client.get("/api/v1/detect?aoi=mumbai&date=2026-04-15")
      assert response.status_code == 200
      data = response.json()
      assert data["type"] == "FeatureCollection"
      for feature in data["features"]:
          assert "properties" in feature
          assert "conf_raw" in feature["properties"]  # PRD schema
  ```

**No Latency/Performance Regression Tests:**
- Untested area: Inference latency is not benchmarked. PRD §11.1 specifies ≤5 sec target; no automated test enforces this.
- Files: Not yet written
- Risk: After adding real inference code, latency will creep up (model optimization, caching, etc. come last). Demo time-slider may stall.
- Priority: MEDIUM — add `pytest-benchmark` to requirements.txt and create:
  ```python
  @pytest.mark.benchmark
  def test_inference_latency(benchmark):
      result = benchmark(inference_pipeline.run, tile_path)
      assert result.time < 5.0  # 5 seconds
  ```

---

## Summary: Prioritized Action Items

| Issue | Phase | Effort | Risk | Action |
|-------|-------|--------|------|--------|
| API contract drift (aoi_id vs. aoi+date) | H16–H28 | 2 hrs | **HIGH** | Reconcile endpoint signatures with PRD §Appendix B before integration. |
| Missing /aois endpoint | H16–H28 | 1 hr | **HIGH** | Add GET /aois endpoint; return 4 AOI metadata objects. |
| Non-idiomatic error handling | H28–H40 | 1 hr | MED | Replace dict returns with HTTPException. |
| MARIDA exposed in .gitignore | H0–H4 | 15 min | **HIGH** | Add MARIDA/ to .gitignore; verify not yet committed. |
| Python version constraint not enforced | H0–H4 | 30 min | MED | Add `python_requires` to setup.py or pyproject.toml. |
| CMEMS/ERA5 registration not done | H0–H4 | 2 hrs | **CRITICAL** | Register accounts; download 7-day slices for demo AOIs. |
| Mock schema mismatches real schema | H16–H28 | 1 hr | **HIGH** | Update mock_data.py to match PRD feature schema. |
| Kaggle kernel config missing | H0–H4 | 1 hr | MED | Create kaggle.json with GPU enabled if training on Kaggle. |
| Physics validation tests missing | H4–H16 | 2 hrs | **CRITICAL** | Write unit test for Lagrangian displacement (0.5 m/s × 24h = 43.2 km). |
| No testing framework | H0–H4 | 30 min | MED | Add pytest to requirements.txt. Create tests/ directory. |
| Model weights distribution plan missing | H4–H16 | 1 hr | **CRITICAL** | Decide on weights storage (Drive, Kaggle, GitHub Releases); document in README. |

---

*Concerns audit: 2026-04-17*
