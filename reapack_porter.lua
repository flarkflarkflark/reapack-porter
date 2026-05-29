#!/usr/bin/env lua

local is_windows = package.config:sub(1, 1) == "\\"
local sep = package.config:sub(1, 1)
local has_reaper = type(reaper) == "table"

local function path_join(a, b)
  if a:sub(-1) == sep then
    return a .. b
  end
  return a .. sep .. b
end

local function dirname(path)
  return path:match("^(.*)[/\\][^/\\]+$") or "."
end

local function basename(path)
  return path:match("([^/\\]+)$") or path
end

local function file_exists(path)
  local f = io.open(path, "rb")
  if f then f:close() return true end
  return false
end

local function path_exists(path)
  local ok = os.rename(path, path)
  return ok == true
end

local function unique_timestamped_path(base_path)
  local stem = base_path .. "." .. os.date("%Y%m%d-%H%M%S")
  if not path_exists(stem) then
    return stem
  end
  for i = 1, 999 do
    local candidate = stem .. "-" .. i
    if not path_exists(candidate) then
      return candidate
    end
  end
  error("Could not create a unique timestamped path")
end

local function read_all(path)
  local f, err = io.open(path, "rb")
  if not f then return nil, err end
  local data = f:read("*a")
  f:close()
  return data
end

local function write_all(path, data)
  local f, err = io.open(path, "wb")
  if not f then return nil, err end
  f:write(data)
  f:close()
  return true
end

local function ensure_dir(path)
  if is_windows then
    os.execute(('mkdir "%s" >NUL 2>NUL'):format(path))
  else
    os.execute(('mkdir -p "%s" >/dev/null 2>&1'):format(path))
  end
end

local function trim(s)
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function sort_case_insensitive(lines)
  table.sort(lines, function(a, b) return a:lower() < b:lower() end)
end

local function detect_reaper_ini_path()
  local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
  if has_reaper and reaper.GetResourcePath then
    return path_join(reaper.GetResourcePath(), "reapack.ini")
  end
  if is_windows then
    local appdata = os.getenv("APPDATA")
    if appdata and appdata ~= "" then
      return path_join(path_join(appdata, "REAPER"), "reapack.ini")
    end
  end
  if home:match("/Users/") then
    return path_join(path_join(path_join(home, "Library"), "Application Support"), "REAPER") .. sep .. "reapack.ini"
  end
  return path_join(path_join(path_join(home, ".config"), "REAPER"), "reapack.ini")
end

local function detect_documents_path()
  local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
  local docs = path_join(home, "Documents")
  return docs
end

local function parse_remotes(ini_text)
  local in_remotes = false
  local remotes = {}
  for line in ini_text:gmatch("[^\r\n]+") do
    local section = line:match("^%[(.-)%]$")
    if section then
      in_remotes = (section == "remotes")
    elseif in_remotes then
      local _, value = line:match("^(remote%d+)=(.+)$")
      if value then
        local a, b, c, d = value:match("^(.-)|(.-)|(.-)|(.+)$")
        if a and b and c and d then
          remotes[#remotes + 1] = {
            name = trim(a),
            url = trim(b),
            enabled = trim(c),
            autosync = trim(d),
          }
        end
      end
    end
  end
  return remotes
end

local function normalize_url(url)
  return trim(url or ""):lower():gsub("/+$", "")
end

local function merge_remotes(existing_remotes, imported_remotes)
  local seen = {}
  local merged = {}
  local added = 0
  local skipped = 0

  for _, remote in ipairs(existing_remotes) do
    merged[#merged + 1] = remote
    seen[normalize_url(remote.url)] = true
  end

  for _, remote in ipairs(imported_remotes) do
    local key = normalize_url(remote.url)
    if key ~= "" and not seen[key] then
      merged[#merged + 1] = remote
      seen[key] = true
      added = added + 1
    else
      skipped = skipped + 1
    end
  end

  return merged, added, skipped
end

local function build_remotes_section(remotes)
  local out = {"[remotes]"}
  for i, r in ipairs(remotes) do
    out[#out + 1] = ("remote%d=%s|%s|%s|%s"):format(i - 1, r.name, r.url, r.enabled, r.autosync)
  end
  out[#out + 1] = ("size=%d"):format(#remotes)
  return table.concat(out, "\n") .. "\n"
end

local function remove_remotes_section(ini_text)
  local out = {}
  local in_remotes = false
  for line in (ini_text .. "\n"):gmatch("([^\n]*)\n") do
    local section = line:match("^%[(.-)%]$")
    if section == "remotes" then
      in_remotes = true
    elseif section and in_remotes then
      in_remotes = false
      out[#out + 1] = line
    elseif not in_remotes then
      out[#out + 1] = line
    end
  end
  return table.concat(out, "\n"):gsub("\n+$", "\n")
end

local function usage()
  io.write([[
ReaPack repo portability tool (Lua)

Usage:
  lua scripts/reapack_porter.lua export [--source <reapack.ini>] [--out <dir>] [--zip]
  lua scripts/reapack_porter.lua import --bundle <dir-or-zip> [--target <reapack.ini>]
  lua scripts/reapack_porter.lua gui
  lua scripts/reapack_porter.lua dialog
  lua scripts/reapack_porter.lua help

Notes:
  - In REAPER (ReaScript), running without arguments opens the best available UI.
  - ReaImGui is used when installed, otherwise the script falls back to simple dialogs.
]])
end

local function parse_kv_args(argv, start_idx)
  local opts, i = {}, start_idx
  while i <= #argv do
    local key = argv[i]
    if key == "--zip" then
      opts[key] = "1"
      i = i + 1
    else
      if key:sub(1, 2) ~= "--" then error("Unknown argument: " .. key) end
      local value = argv[i + 1]
      if not value or value:sub(1, 2) == "--" then error("Missing value for " .. key) end
      opts[key] = value
      i = i + 2
    end
  end
  return opts
end

local function open_folder(path)
  path = trim(path or "")
  if path == "" then
    return false, "No folder path available."
  end

  local folder = path
  if file_exists(path) then
    folder = dirname(path)
  end

  local ok
  if is_windows then
    ok = os.execute(('explorer "%s"'):format(folder))
  elseif has_reaper and reaper.GetOS and tostring(reaper.GetOS()):lower():match("osx") then
    ok = os.execute(('open "%s" >/dev/null 2>&1'):format(folder))
  else
    ok = os.execute(('xdg-open "%s" >/dev/null 2>&1'):format(folder))
  end

  if ok then
    return true, "Opened folder: " .. folder
  end
  return false, "Could not open folder: " .. folder
end

local function remove_tree(path)
  path = trim(path or "")
  if path == "" then
    return false
  end

  local ok
  if is_windows then
    ok = os.execute(('rmdir /S /Q "%s"'):format(path))
  else
    ok = os.execute(('rm -rf "%s"'):format(path))
  end
  return ok == true or ok == 0
end

local function zip_bundle(bundle_dir)
  local parent = dirname(bundle_dir)
  local base = bundle_dir:match("([^/\\]+)$") or bundle_dir
  local zip_path = path_join(parent, base .. ".zip")

  local ok
  if is_windows then
    local cmd = ([[powershell -NoProfile -Command "Compress-Archive -Path '%s' -DestinationPath '%s' -Force"]]):format(bundle_dir, zip_path)
    ok = os.execute(cmd)
  else
    local cmd = ('cd "%s" && zip -r "%s.zip" "%s" >/dev/null 2>&1'):format(parent, base, base)
    ok = os.execute(cmd)
  end

  if not ok or not file_exists(zip_path) then
    return nil, "ZIP creation failed (missing zip tool or command failed)."
  end
  return zip_path, nil
end

local function is_zip_path(path)
  return path:lower():match("%.zip$") ~= nil
end

local function extract_zip_bundle(zip_path)
  if not file_exists(zip_path) then
    error("ZIP file not found: " .. zip_path)
  end

  local parent = dirname(zip_path)
  local base = (zip_path:match("([^/\\]+)$") or "reapack-portable.zip"):gsub("%.zip$", "")
  local extract_dir
  for i = 0, 999 do
    local suffix = i == 0 and "" or ("-" .. i)
    local candidate = path_join(parent, base .. "-extracted-" .. os.date("%Y%m%d-%H%M%S") .. suffix)
    if not path_exists(candidate) then
      extract_dir = candidate
      break
    end
  end
  if not extract_dir then
    error("Could not create a unique extraction folder")
  end
  ensure_dir(extract_dir)

  local ok
  if is_windows then
    local cmd = ([[powershell -NoProfile -Command "Expand-Archive -Path '%s' -DestinationPath '%s' -Force"]]):format(zip_path, extract_dir)
    ok = os.execute(cmd)
  else
    local cmd = ('unzip -oq "%s" -d "%s"'):format(zip_path, extract_dir)
    ok = os.execute(cmd)
  end

  if not ok then
    error("Could not extract ZIP. Ensure unzip (Linux/macOS) or PowerShell Expand-Archive (Windows) is available.")
  end

  local nested_bundle = path_join(extract_dir, base)
  if file_exists(path_join(nested_bundle, "remotes_section.ini")) then
    return nested_bundle
  end
  if file_exists(path_join(extract_dir, "remotes_section.ini")) then
    return extract_dir
  end
  error("Extracted ZIP does not contain remotes_section.ini")
end

local function zip_contains_remotes_section(zip_path)
  if not file_exists(zip_path) then
    return false, "ZIP file not found."
  end

  local ok
  if is_windows then
    local cmd = ([[powershell -NoProfile -Command "$z='%s'; Add-Type -AssemblyName System.IO.Compression.FileSystem; $a=[System.IO.Compression.ZipFile]::OpenRead($z); $ok=$false; foreach($e in $a.Entries){ if($e.FullName -match '(^|/)remotes_section\.ini$'){ $ok=$true } }; $a.Dispose(); if($ok){ exit 0 } else { exit 1 }"]]):format(zip_path)
    ok = os.execute(cmd)
  else
    local cmd = ('unzip -l "%s" remotes_section.ini "*/remotes_section.ini" >/dev/null 2>&1'):format(zip_path)
    ok = os.execute(cmd)
  end

  if ok then
    return true, "Valid ReaPack Porter ZIP."
  end
  return false, "ZIP does not contain remotes_section.ini."
end

local function validate_import_source(bundle)
  bundle = trim(bundle or "")
  if bundle == "" then
    return false, "Select a bundle folder or ZIP file."
  end
  if is_zip_path(bundle) then
    return zip_contains_remotes_section(bundle)
  end
  local remotes_path = path_join(bundle, "remotes_section.ini")
  if file_exists(remotes_path) then
    return true, "Valid bundle folder."
  end
  return false, "Folder does not contain remotes_section.ini."
end

local function export_bundle(source, out_dir)
  if not file_exists(source) then error("Source file not found: " .. source) end
  ensure_dir(out_dir)

  local ts = os.date("%Y%m%d-%H%M%S")
  local bundle_dir = path_join(out_dir, "reapack-portable-" .. ts)
  ensure_dir(bundle_dir)

  local ini_text = assert(read_all(source))
  local remotes = parse_remotes(ini_text)
  if #remotes == 0 then error("No remotes found in [remotes] section.") end

  local sortable = {}
  for _, r in ipairs(remotes) do
    sortable[#sortable + 1] = ("%s\t%s\t%s\t%s"):format(r.name, r.url, r.enabled, r.autosync)
  end
  sort_case_insensitive(sortable)

  local sorted_remotes, repos_tsv, repos_urls = {}, {}, {}
  for _, line in ipairs(sortable) do
    local a, b, c, d = line:match("^(.-)\t(.-)\t(.-)\t(.+)$")
    sorted_remotes[#sorted_remotes + 1] = { name = a, url = b, enabled = c, autosync = d }
    repos_tsv[#repos_tsv + 1] = line
    repos_urls[#repos_urls + 1] = b
  end

  assert(write_all(path_join(bundle_dir, "repos.tsv"), table.concat(repos_tsv, "\n") .. "\n"))
  assert(write_all(path_join(bundle_dir, "repos_urls.txt"), table.concat(repos_urls, "\n") .. "\n"))
  assert(write_all(path_join(bundle_dir, "remotes_section.ini"), build_remotes_section(sorted_remotes)))

  local readme = ([[ReaPack portable export
Generated: %s
Source: %s
Repos: %d

Files:
- repos_urls.txt      URLs only, one per line
- remotes_section.ini complete [remotes] section

Import:
1) Close REAPER.
2) Run this command:
   lua scripts/reapack_porter.lua import --bundle "%s"
3) Start REAPER and run ReaPack > Synchronize packages.
]]):format(os.date("!%Y-%m-%dT%H:%M:%SZ"), source, #sorted_remotes, bundle_dir)
  assert(write_all(path_join(bundle_dir, "README_IMPORT.txt"), readme))

  return bundle_dir, #sorted_remotes
end

local function import_bundle(bundle, target)
  if is_zip_path(bundle) then
    bundle = extract_zip_bundle(bundle)
  end

  local remotes_path = path_join(bundle, "remotes_section.ini")
  if not file_exists(remotes_path) then error("Missing file: " .. remotes_path) end

  local remotes_text = assert(read_all(remotes_path))
  local imported_remotes = parse_remotes(remotes_text)
  if #imported_remotes == 0 then
    error("No repositories found in imported remotes_section.ini")
  end

  local old_ini
  if file_exists(target) then
    old_ini = assert(read_all(target))
  else
    ensure_dir(dirname(target))
    old_ini = "[general]\nversion=4\n"
  end

  local backup = unique_timestamped_path(target .. ".bak")
  assert(write_all(backup, old_ini))

  local existing_remotes = parse_remotes(old_ini)
  local merged_remotes, added, skipped = merge_remotes(existing_remotes, imported_remotes)
  local stripped = remove_remotes_section(old_ini)
  local merged = stripped:gsub("\n*$", "\n") .. "\n" .. build_remotes_section(merged_remotes)
  assert(write_all(target, merged))

  return backup, added, skipped, #merged_remotes
end

local function do_export(argv)
  local opts = parse_kv_args(argv, 2)
  local source = opts["--source"] or detect_reaper_ini_path()
  local out_dir = opts["--out"] or detect_documents_path()
  local want_zip = opts["--zip"] == "1"
  local bundle, count = export_bundle(source, out_dir)
  io.write("OK: exported ", count, " repositories\n")
  io.write("Bundle: ", bundle, "\n")
  if want_zip then
    local zip_path, zip_err = zip_bundle(bundle)
    if zip_path then
      io.write("ZIP: ", zip_path, "\n")
      if remove_tree(bundle) then
        io.write("Removed temporary folder: ", bundle, "\n")
      else
        io.write("WARN: Could not remove temporary folder: ", bundle, "\n")
      end
    else
      io.write("WARN: ", zip_err, "\n")
      io.write("WARN: Exported folder is still usable: ", bundle, "\n")
    end
  end
end

local function do_import(argv)
  local opts = parse_kv_args(argv, 2)
  local bundle = opts["--bundle"]
  local target = opts["--target"] or detect_reaper_ini_path()
  if not bundle then error("Missing required --bundle <dir>") end
  local backup, added, skipped, total = import_bundle(bundle, target)
  io.write("OK: imported remotes into ", target, "\n")
  io.write("Backup: ", backup, "\n")
  io.write("Added: ", added, "\n")
  io.write("Already existed: ", skipped, "\n")
  io.write("Total repositories: ", total, "\n")
end

local function run_dialog_mode()
  if not has_reaper or not reaper.GetUserInputs then
    error("Dialog mode requires running inside REAPER (ReaScript)")
  end

  local ok_mode, mode = reaper.GetUserInputs("ReaPack Repo Tool", 1, "Mode (export/import)", "export")
  if not ok_mode then return end
  mode = trim((mode or ""):lower())

  if mode == "export" then
    local default_source = detect_reaper_ini_path()
    local default_out = detect_documents_path()
    local ok, vals = reaper.GetUserInputs("Export ReaPack Repos", 2, "Source reapack.ini,Output folder", default_source .. "," .. default_out)
    if not ok then return end
    local source, out_dir = vals:match("^(.-),(.*)$")
    source, out_dir = trim(source or ""), trim(out_dir or "")
    local ok_zip, zip_answer = reaper.GetUserInputs("Export ZIP?", 1, "Create ZIP too? (yes/no)", "yes")
    if not ok_zip then return end
    local want_zip = trim((zip_answer or ""):lower()) ~= "no"
    local bundle, count = export_bundle(source, out_dir)
    local msg = ("Exported %d repositories\n\nBundle:\n%s"):format(count, bundle)
    if want_zip then
      local zip_path, zip_err = zip_bundle(bundle)
      if zip_path then
        msg = msg .. ("\n\nZIP:\n%s"):format(zip_path)
        remove_tree(bundle)
      else
        msg = msg .. ("\n\nZIP warning:\n%s\n\nFolder export still works."):format(zip_err)
      end
    end
    reaper.MB(msg, "ReaPack Repo Tool", 0)
    return
  end

  if mode == "import" then
    local default_target = detect_reaper_ini_path()
    local ok, vals = reaper.GetUserInputs("Import ReaPack Repos", 2, "Bundle folder or ZIP file,Target reapack.ini", "," .. default_target)
    if not ok then return end
    local bundle, target = vals:match("^(.-),(.*)$")
    bundle, target = trim(bundle or ""), trim(target or "")
    if bundle == "" then error("Bundle folder is required") end
    local backup, added, skipped, total = import_bundle(bundle, target)
    reaper.MB(("Import completed\n\nTarget:\n%s\n\nBackup:\n%s\n\nAdded: %d\nAlready existed: %d\nTotal repositories: %d"):format(target, backup, added, skipped, total), "ReaPack Repo Tool", 0)
    return
  end

  error("Mode must be 'export' or 'import'")
end

local function can_use_imgui()
  return has_reaper and reaper.APIExists and reaper.APIExists("ImGui_GetVersion") and reaper.ImGui_GetBuiltinPath
end

local function run_imgui_mode()
  if not can_use_imgui() then
    run_dialog_mode()
    return
  end

  package.path = reaper.ImGui_GetBuiltinPath() .. "/?.lua;" .. package.path
  local ImGui = require("imgui")("0.10")
  local ctx = ImGui.CreateContext("ReaPack Porter")

  local state = {
    tab = "export",
    source = detect_reaper_ini_path(),
    out_dir = detect_documents_path(),
    create_zip = true,
    keep_folder_after_zip = false,
    last_export_path = "",
    bundle = "",
    import_valid = false,
    import_valid_msg = "Select a bundle folder or ZIP file.",
    target = detect_reaper_ini_path(),
    status = "Ready.",
    status_detail = "",
    status_kind = "info",
  }

  local function refresh_import_validation()
    state.import_valid, state.import_valid_msg = validate_import_source(state.bundle)
  end

  local function path_input(label, id, value)
    ImGui.Text(ctx, label)
    ImGui.SetNextItemWidth(ctx, -1)
    local changed, new_value = ImGui.InputText(ctx, "##" .. id, value)
    return changed, new_value
  end

  local function show_status()
    local colors = {
      info = 0x9FB3C8FF,
      success = 0x36D46DFF,
      warning = 0xE0B84AFF,
      error = 0xE45C5CFF,
    }
    ImGui.TextColored(ctx, colors[state.status_kind] or colors.info, state.status)
    if state.status_detail ~= "" then
      ImGui.TextColored(ctx, 0x9FB3C8FF, state.status_detail)
    end
    ImGui.Separator(ctx)
  end

  local function set_status(kind, message, detail)
    state.status_kind = kind
    state.status = message
    state.status_detail = detail or ""
  end

  local function loop()
    ImGui.SetNextWindowSize(ctx, 680, 430, ImGui.Cond_FirstUseEver)
    ImGui.SetNextWindowSizeConstraints(ctx, 520, 360, 1400, 1000)
    local window_flags = (ImGui.WindowFlags_NoScrollbar or 0) | (ImGui.WindowFlags_NoScrollWithMouse or 0)
    local visible, open = ImGui.Begin(ctx, "ReaPack Porter", true, window_flags)
    if visible then
      if ImGui.BeginTabBar(ctx, "mode_tabs") then
        if ImGui.BeginTabItem(ctx, "Export") then
          state.tab = "export"
          ImGui.Text(ctx, "Export ReaPack repositories")
          show_status()
          ImGui.Spacing(ctx)

          local changed_source, source = path_input("Source reapack.ini", "source", state.source)
          if changed_source then state.source = source end

          local changed_out, out_dir = path_input("Output folder", "out_dir", state.out_dir)
          if changed_out then state.out_dir = out_dir end
          if has_reaper and reaper.APIExists and reaper.APIExists("JS_Dialog_BrowseForFolder") then
            if ImGui.Button(ctx, "Browse output...", 150, 0) then
              local ok_folder, folder = reaper.JS_Dialog_BrowseForFolder("Select export output folder", state.out_dir ~= "" and state.out_dir or detect_documents_path())
              if ok_folder and folder and folder ~= "" then
                state.out_dir = folder
                set_status("info", "Selected output folder", basename(folder))
              end
            end
          end

          ImGui.Spacing(ctx)
          local changed_zip, create_zip = ImGui.Checkbox(ctx, "Create zip file", state.create_zip)
          if changed_zip then state.create_zip = create_zip end
          if state.create_zip then
            local changed_keep, keep_folder = ImGui.Checkbox(ctx, "Keep folder after zip", state.keep_folder_after_zip)
            if changed_keep then state.keep_folder_after_zip = keep_folder end
          end

          ImGui.Spacing(ctx)
          if ImGui.Button(ctx, "Export", 120, 0) then
            local ok, result_or_err, detail = pcall(function()
              local bundle, count = export_bundle(trim(state.source), trim(state.out_dir))
              state.last_export_path = bundle
              local msg = ("Exported %d repositories"):format(count)
              local short_detail = "Bundle: " .. basename(bundle)
              if state.create_zip then
                local zip_path, zip_err = zip_bundle(bundle)
                if zip_path then
                  state.last_export_path = zip_path
                  short_detail = "ZIP: " .. basename(zip_path)
                  if not state.keep_folder_after_zip then
                    remove_tree(bundle)
                  end
                else
                  short_detail = "ZIP warning: " .. tostring(zip_err)
                end
              end
              return msg, short_detail
            end)
            if ok then
              set_status("success", result_or_err, detail)
            else
              set_status("error", tostring(result_or_err))
            end
          end

          ImGui.SameLine(ctx)
          if ImGui.Button(ctx, "Reset paths", 120, 0) then
            state.source = detect_reaper_ini_path()
            state.out_dir = detect_documents_path()
            set_status("info", "Paths reset.")
          end

          if state.last_export_path ~= "" then
            ImGui.SameLine(ctx)
            if ImGui.Button(ctx, "Open output folder", 170, 0) then
              local ok_open, msg = open_folder(state.last_export_path)
              set_status(ok_open and "success" or "warning", msg)
            end
          end

          ImGui.EndTabItem(ctx)
        end

        if ImGui.BeginTabItem(ctx, "Import") then
          state.tab = "import"
          ImGui.Text(ctx, "Import ReaPack repositories")
          show_status()
          ImGui.Spacing(ctx)

          local changed_bundle, bundle = path_input("Bundle folder or ZIP file", "bundle", state.bundle)
          if changed_bundle then
            state.bundle = bundle
            refresh_import_validation()
          end

          local has_folder_browse = has_reaper and reaper.APIExists and reaper.APIExists("JS_Dialog_BrowseForFolder")
          if reaper.GetUserFileNameForRead then
            if ImGui.Button(ctx, "Browse ZIP...", 120, 0) then
              local ok_file, file = reaper.GetUserFileNameForRead(state.bundle or "", "Select ReaPack Porter ZIP", ".zip")
              if ok_file and file and file ~= "" then
                state.bundle = file
                refresh_import_validation()
                set_status(state.import_valid and "success" or "warning", "Selected ZIP", basename(file))
              end
            end
            if has_folder_browse then
              ImGui.SameLine(ctx)
            end
          end
          if has_folder_browse then
            if ImGui.Button(ctx, "Browse folder...", 140, 0) then
              local ok_folder, folder = reaper.JS_Dialog_BrowseForFolder("Select ReaPack Porter bundle folder", dirname(state.bundle ~= "" and state.bundle or detect_documents_path()))
              if ok_folder and folder and folder ~= "" then
                state.bundle = folder
                refresh_import_validation()
                set_status(state.import_valid and "success" or "warning", "Selected folder", basename(folder))
              end
            end
          end

          ImGui.Spacing(ctx)
          if state.import_valid then
            ImGui.TextColored(ctx, 0x36D46DFF, "OK: " .. state.import_valid_msg)
          else
            ImGui.TextColored(ctx, 0xE0B84AFF, state.import_valid_msg)
          end

          local changed_target, target = path_input("Target reapack.ini", "target", state.target)
          if changed_target then state.target = target end
          ImGui.TextColored(ctx, 0x9FB3C8FF, "A timestamped backup is created before import.")

          ImGui.Spacing(ctx)
          if ImGui.Button(ctx, "Import", 120, 0) then
            local ok, result_or_err, detail = pcall(function()
              local backup, added, skipped, total = import_bundle(trim(state.bundle), trim(state.target))
              return ("Imported. Added %d, existing %d, total %d"):format(added, skipped, total), "Backup: " .. basename(backup)
            end)
            if ok then
              set_status("success", result_or_err, detail)
            else
              set_status("error", tostring(result_or_err))
            end
          end

          ImGui.SameLine(ctx)
          if ImGui.Button(ctx, "Reset target", 120, 0) then
            state.target = detect_reaper_ini_path()
            set_status("info", "Target reset.")
          end

          ImGui.EndTabItem(ctx)
        end
        ImGui.EndTabBar(ctx)
      end
      ImGui.End(ctx)
    end

    if open then
      reaper.defer(loop)
    end
  end

  reaper.defer(loop)
end

local function main(argv)
  argv = argv or {}
  local cmd = argv[1]
  if not cmd and has_reaper then
    run_imgui_mode()
    return
  end
  cmd = cmd or "help"
  if cmd == "help" or cmd == "-h" or cmd == "--help" then usage(); return end
  if cmd == "export" then do_export(argv); return end
  if cmd == "import" then do_import(argv); return end
  if cmd == "dialog" then run_dialog_mode(); return end
  if cmd == "gui" then run_imgui_mode(); return end
  error("Unknown command: " .. cmd)
end

local ok, err = pcall(function() main(arg) end)
if not ok then
  if has_reaper and reaper.MB then
    reaper.MB(tostring(err), "ReaPack Repo Tool - Error", 0)
  else
    io.stderr:write("ERROR: ", tostring(err), "\n")
  end
  os.exit(1)
end
