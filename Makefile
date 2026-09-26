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

.DEFAULT_GOAL := all
