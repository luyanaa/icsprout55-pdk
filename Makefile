# =============================================================================
# Extract blocks
# =============================================================================
ORGS_NAME := openecos-projects
REPO_NAME := icsprout55-pdk

PROXY_URL ?= https://gh-proxy.org/
PROXY_USE ?= false

RELEASE_TAG ?= latest
RELEASE_FILE_LIB := ics55_LLSC_H7CH_liberty.tar.bz2 \
                    ics55_LLSC_H7CL_liberty.tar.bz2 \
                    ics55_LLSC_H7CR_liberty.tar.bz2

RELEASE_FILE_GDS_STD := ics55_LLSC_H7CH_gds.tar.bz2 \
                        ics55_LLSC_H7CL_gds.tar.bz2 \
                        ics55_LLSC_H7CR_gds.tar.bz2
RELEASE_FILE_GDS_IO := ICsprout_55LLULP1233_IO_251013_gds.tar.bz2
RELEASE_FILE_GDS    := $(RELEASE_FILE_GDS_STD) $(RELEASE_FILE_GDS_IO)
RELEASE_FILE        := $(RELEASE_FILE_LIB) $(RELEASE_FILE_GDS)
LIBS_REF := libs.ref
STD_CELL_VARIANTS := ics55_LLSC_H7CR ics55_LLSC_H7CL ics55_LLSC_H7CH

DECOMP_DIR_LIB_P := $(LIBS_REF)
DECOMP_DIR_LIB   := $(patsubst %_liberty.tar.bz2, $(DECOMP_DIR_LIB_P)/%/liberty, $(RELEASE_FILE_LIB))

DECOMP_DIR_GDS_STD_P := $(LIBS_REF)
DECOMP_DIR_GDS_IO_P  := $(LIBS_REF)
DECOMP_DIR_GDS       := $(patsubst %_gds.tar.bz2, $(DECOMP_DIR_GDS_STD_P)/%/gds, $(RELEASE_FILE_GDS_STD)) \
                        $(patsubst %_gds.tar.bz2, $(DECOMP_DIR_GDS_IO_P)/%/gds, $(RELEASE_FILE_GDS_IO))

DECOMP_DIR := $(DECOMP_DIR_LIB) $(DECOMP_DIR_GDS)

.PHONY: start download unzip clean-bz2 clean-dir

$(RELEASE_FILE):
	@echo "\n[download] getting release info for $(RELEASE_TAG)"
	@if [ "$(RELEASE_TAG)" = "latest" ]; then \
		API_PATH="releases/latest"; \
	else \
		API_PATH="releases/tags/$(RELEASE_TAG)"; \
	fi; \
	RELEASE_URL=$$(curl -s "https://api.github.com/repos/$(ORGS_NAME)/$(REPO_NAME)/$$API_PATH" | \
		grep -E "browser_download_url.*$(@)" | \
		cut -d '"' -f 4); \
	if [ -z "$$RELEASE_URL" ]; then \
		echo "[download] file not found $(@)"; \
		echo "[download] please check whether the Release contains the following files: "; \
		echo "$(RELEASE_FILE)"; \
		exit 1; \
	fi; \
	echo "[download] getting $(@)..."; \
	if [ "$(PROXY_USE)" = "true" ]; then \
		RELEASE_URL="$(PROXY_URL)$$RELEASE_URL"; \
	fi; \
	if [ "$(TOOL)" = "wget" ]; then \
		wget -O "$(@).part" "$$RELEASE_URL"; \
	else \
		curl -fL -o "$(@).part" "$$RELEASE_URL"; \
	fi || { rm -f "$(@).part"; exit 1; }; \
	mv "$(@).part" "$(@)"; \
	echo "[download] done!"

$(DECOMP_DIR_LIB_P)/%/liberty: %_liberty.tar.bz2
	@echo "\n[unzip] decompressing: $< -> $(DECOMP_DIR_LIB_P)/$*/"
	@mkdir -p $@
	@tar -xjvf $< -C $(DECOMP_DIR_LIB_P)/$*/
	@touch $@

$(DECOMP_DIR_GDS_STD_P)/%/gds: %_gds.tar.bz2
	@echo "\n[unzip] decompressing: $< -> $(DECOMP_DIR_GDS_STD_P)/$*/"
	@mkdir -p $@
	@tar -xjvf $< -C $(DECOMP_DIR_GDS_STD_P)/$*/
	@touch $@

$(DECOMP_DIR_GDS_IO_P)/%/gds: %_gds.tar.bz2
	@echo "\n[unzip] decompressing: $< -> $(DECOMP_DIR_GDS_IO_P)/$*/"
	@mkdir -p $@
	@tar -xjvf $< -C $(DECOMP_DIR_GDS_IO_P)/$*/
	@touch $@

unzip: start $(DECOMP_DIR)
	@$(MAKE) --no-print-directory clean-bz2
	@echo "\n[unzip] done!"

start:
	@echo "[unzip] start..."

download: $(RELEASE_FILE)

clean-bz2:
	@echo "\n[clean] delete compressed files"
	@find ./ -name "*.tar.bz2" -exec rm -fv {} \; || true

clean-dir:
	@echo "\n[clean] delete decompressed dirs"
	@find $(LIBS_REF) -depth -type d -name "liberty" -path "*/ics55_LLSC_H7C*" -exec rm -rfv {} \; || true
	@find $(LIBS_REF) -depth -type d -name "gds" -exec rm -rfv {} \; || true


# =============================================================================
# Default goal: download + extract the release archives into libs.ref
# =============================================================================
# libs.ref is the real home of the digital-PDK views:
#   - cdl, cell_list, doc, lef, verilog + IO liberty are tracked in git
#   - gds + std-cell liberty are large binaries downloaded from the release
#   archives (this Makefile) and gitignored
# A fresh clone + `make` yields a ready std-cell library.
# Existing release views are left intact; use `make clean-dir` to force refresh.
.PHONY: all
all: unzip

.PHONY: stage-libs-ref
stage-libs-ref:
	@for lib in $(STD_CELL_VARIANTS); do \
	  python3 libs.tech/pex/config_gen.py --openrcx --layers-rc --scl $$lib; \
	done
	@echo "RCX configs regenerated for $(STD_CELL_VARIANTS)."

# Memory IPs are release assets. ROM is small enough to fetch as a catalog;
# SRAM packages are selected explicitly because the catalog is much larger.
MACRO_API_ROOT := https://api.github.com/repos/openecos-projects
MACRO_FORCE ?= false
SRAM_ASSETS ?=

.PHONY: unzip-macros unzip-sram list-sram-assets _fetch-memory-macros
unzip-macros:
	@$(MAKE) --no-print-directory _fetch-memory-macros MACRO_MODE=rom SRAM_ASSETS='$(SRAM_ASSETS)'

unzip-sram:
	@$(MAKE) --no-print-directory _fetch-memory-macros MACRO_MODE=sram SRAM_ASSETS='$(SRAM_ASSETS)'

list-sram-assets:
	@$(MAKE) --no-print-directory _fetch-memory-macros MACRO_MODE=list-sram

_fetch-memory-macros:
	@set -eu; set -f; \
	  stage=$$(mktemp -d "$(LIBS_REF)/.ecos-macros.XXXXXX"); \
	  trap 'rm -rf "$$stage"' EXIT HUP INT TERM; \
	  mode='$(MACRO_MODE)'; \
	  sram_assets='$(SRAM_ASSETS)'; \
	  case "$$mode" in \
	    rom) repos=ics55_ecos_rom; if [ -n "$$sram_assets" ]; then repos="$$repos ics55_ecos_sram"; fi ;; \
	    sram|list-sram) repos=ics55_ecos_sram ;; \
	    *) echo "[macros] unknown mode: $$mode" >&2; exit 1 ;; \
	  esac; \
	  if [ "$$mode" = sram ] && [ -z "$$sram_assets" ]; then \
	    echo '[macros] select one or more packages: make unzip-sram SRAM_ASSETS="asset.tar.gz ..."'; \
	    exit 2; \
	  fi; \
	  for repo in $$repos; do \
	    case "$$repo" in \
	      ics55_ecos_rom) kind=rom; tag_prefix=rom-v1-; package_prefix=ics55_ecos_rom_ ;; \
	      ics55_ecos_sram) kind=sram; tag_prefix=sram-v1-; package_prefix=ics55_ecos_sram_ ;; \
	    esac; \
	    catalog="$$stage/$$repo-catalog.tsv"; \
	    : > "$$catalog"; \
	    page=1; \
	    while :; do \
	      response="$$stage/$$repo-page-$$page.json"; \
	      if [ -n "$${GITHUB_TOKEN:-}" ]; then \
	        saved_umask=$$(umask); umask 077; \
	        printf 'header = "Authorization: Bearer %s"\n' "$$GITHUB_TOKEN" > "$$stage/github-auth.curl"; \
	        umask "$$saved_umask"; \
	        http_code=$$(curl -sS -L --config "$$stage/github-auth.curl" -o "$$response" -w '%{http_code}' "$(MACRO_API_ROOT)/$$repo/releases?per_page=100&page=$$page"); \
	      else \
	        http_code=$$(curl -sS -L -o "$$response" -w '%{http_code}' "$(MACRO_API_ROOT)/$$repo/releases?per_page=100&page=$$page"); \
	      fi; \
	      if [ "$$http_code" != 200 ]; then \
	        echo "[macros] release catalog lookup for $$repo page $$page failed (HTTP $$http_code)" >&2; \
	        cat "$$response" >&2; \
	        exit 1; \
	      fi; \
	      page_count=$$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))))' "$$response"); \
	      if [ "$$page_count" -eq 0 ]; then break; fi; \
	      python3 -c 'import json,sys; rs=json.load(open(sys.argv[1], encoding="utf-8")); p=sys.argv[2]; [print("\t".join((r["tag_name"], r.get("published_at", ""), a["name"], a["browser_download_url"], a.get("digest") or "-", str(a["size"])))) for r in rs if not r.get("draft", False) and r.get("tag_name", "").startswith(p) for a in r.get("assets", []) if a.get("name", "").endswith(".tar.gz")]' "$$response" "$$tag_prefix" >> "$$catalog"; \
	      page=$$((page + 1)); \
	    done; \
	    if [ ! -s "$$catalog" ]; then \
	      echo "[macros] no $$tag_prefix release assets found for $$repo" >&2; \
	      exit 1; \
	    fi; \
	    if [ "$$mode" = list-sram ]; then \
	      python3 -c 'import sys; rows=[x.rstrip("\n").split("\t") for x in open(sys.argv[1], encoding="utf-8")]; rows.sort(key=lambda r:r[1], reverse=True); latest={}; [latest.setdefault(r[2], r) for r in rows]; print("ASSET\tLATEST_RELEASE\tCOMPRESSED_BYTES"); [print("\t".join((n, r[0], r[5]))) for n,r in sorted(latest.items())]' "$$catalog"; \
	      continue; \
	    fi; \
	    selected="$$stage/$$repo-selected.tsv"; \
	    if [ "$$repo" = ics55_ecos_sram ]; then \
	      python3 -c 'import sys; rows=[x.rstrip("\n").split("\t") for x in open(sys.argv[1], encoding="utf-8")]; req=set(sys.argv[2].split()); rows.sort(key=lambda r:r[1], reverse=True); latest={}; [latest.setdefault(r[2], r) for r in rows]; missing=req-set(latest); assert not missing, "unknown SRAM asset(s): "+", ".join(sorted(missing)); [print("\t".join(r)) for n,r in sorted(latest.items()) if n in req]' "$$catalog" "$$sram_assets" > "$$selected"; \
	    else \
	      cp "$$catalog" "$$selected"; \
	    fi; \
	    mkdir -p "$$stage/download/$$repo" "$$stage/extract/$$repo"; \
	    while IFS="$$(printf '\t')" read -r tag published asset url digest size; do \
	      case "$$asset" in *[!A-Za-z0-9._-]*|'') echo "[macros] unsafe asset name: $$asset" >&2; exit 1 ;; esac; \
	      case "$$tag" in "$$tag_prefix"*) version=$${tag#"$$tag_prefix"} ;; *) echo "[macros] unexpected release tag: $$tag" >&2; exit 1 ;; esac; \
	      case "$$version" in *[!A-Fa-f0-9]*|'') echo "[macros] unsafe release id: $$version" >&2; exit 1 ;; esac; \
	      archive="$$stage/download/$$repo/$$asset-$$version.tar.gz"; \
	      curl -fLsS "$$url" -o "$$archive"; \
	      case "$$digest" in \
	        sha256:*) printf '%s  %s\n' "$${digest#sha256:}" "$$archive" | shasum -a 256 -c - ;; \
	        -) echo "[macros] warning: GitHub provides no SHA-256 digest for $$asset" >&2 ;; \
	        *) echo "[macros] unsupported digest for $$asset: $$digest" >&2; exit 1 ;; \
	      esac; \
	      root=$$(python3 -c 'import pathlib,sys,tarfile; t=tarfile.open(sys.argv[1], "r:gz"); ms=t.getmembers(); p=pathlib.PurePosixPath; assert all((m.isfile() or m.isdir()) and not p(m.name).is_absolute() and ".." not in p(m.name).parts for m in ms), "unsafe archive member"; roots={p(m.name).parts[0] for m in ms if p(m.name).parts}; assert len(roots)==1, "archive must contain one top-level directory"; print(next(iter(roots)))' "$$archive"); \
	      case "$$root" in *[!A-Za-z0-9._-]*|'') echo "[macros] unsafe package directory: $$root" >&2; exit 1 ;; esac; \
	      [ "$$root" = "$${asset%.tar.gz}" ] || { echo "[macros] archive root $$root does not match $$asset" >&2; exit 1; }; \
	      case "$$root" in "$$package_prefix"*) ;; *) echo "[macros] package root $$root does not match $$repo" >&2; exit 1 ;; esac; \
	      config=$${root#"$$package_prefix"}; \
	      [ -n "$$config" ] || { echo "[macros] empty IP configuration in $$root" >&2; exit 1; }; \
	      tar -xzf "$$archive" -C "$$stage/extract/$$repo"; \
	      package="$$stage/extract/$$repo/$$root"; \
	      for view in doc lef lib power verilog; do \
	        if [ ! -d "$$package/$$view" ]; then echo "[macros] missing $$view/ in $$asset" >&2; exit 1; fi; \
	      done; \
	      destination="$(LIBS_REF)/icsprout55_fd_$${kind}__$${config}__$${version}"; \
	      if [ -e "$$destination" ]; then \
	        if [ "$(MACRO_FORCE)" = true ]; then rm -rf "$$destination"; \
	        else echo "[macros] keeping existing $$destination (use MACRO_FORCE=true to replace)"; continue; fi; \
	      fi; \
	      legacy="$(LIBS_REF)/$$root"; \
	      if [ -d "$$legacy" ] && [ "$(MACRO_FORCE)" != true ]; then \
	        mv "$$legacy" "$$destination"; \
	        echo "[macros] migrated $$legacy to $$destination"; \
	      else \
	        mv "$$package" "$$destination"; \
	        echo "[macros] installed $$destination"; \
	      fi; \
	      if [ ! -e "$$destination/UPSTREAM.txt" ]; then \
	        printf 'Repository: https://github.com/openecos-projects/%s\nRelease: %s\nPublished: %s\nAsset: %s\nSHA-256: %s\n' "$$repo" "$$tag" "$$published" "$$asset" "$$digest" > "$$destination/UPSTREAM.txt"; \
	      fi; \
	    done < "$$selected"; \
	  done



.DEFAULT_GOAL := all
