-- interface.lua

-- Rectifies issues loading the Factorio toolchain without the game itself.
-- All contents are subject to change.

---@diagnostic disable:lowercase-global
---@diagnostic disable:undefined-global

-- Meta globals: these are used to keep track of ourselves during the load
-- process
MOD_LIST = nil
MOD = nil
MOD_DIR = nil
CURRENT_FILE = nil
CURRENT_DIR = ""

-- Menu simulations: can be empty, but cannot be nil; not included in factorio-
-- data, so we supply dummy values
local menu_simulations = {}
menu_simulations.forest_fire = {}
menu_simulations.solar_power_construction = {}
menu_simulations.lab = {}
menu_simulations.burner_city = {}
menu_simulations.mining_defense = {}
menu_simulations.biter_base_steamrolled = {}
menu_simulations.biter_base_spidertron = {}
menu_simulations.biter_base_artillery = {}
menu_simulations.biter_base_player_attack = {}
menu_simulations.biter_base_laser_defense = {}
menu_simulations.artillery = {}
menu_simulations.train_junction = {}
menu_simulations.oil_pumpjacks = {}
menu_simulations.oil_refinery = {}
menu_simulations.early_smelting = {}
menu_simulations.train_station = {}
menu_simulations.logistic_robots = {}
menu_simulations.nuclear_power = {}
menu_simulations.chase_player = {}
menu_simulations.big_defense = {}
menu_simulations.brutal_defeat = {}
menu_simulations.spider_ponds = {}

-- math.pow deprecated in Lua > 5.3; Factorio uses 5.2. Simple to fix:
-- TODO: should be removed once we switch to lupa 2.0
math.pow = math.pow or function(value, power)
    return value ^ power
end

-- Overwrite print to distinguish which "side" the message came from
local old_print = print
function print(...)
    old_print("LUA:", ...)
end

-- Display any logged messages if logging is enabled. Any error messages are
-- automatially displayed regardless of logging status.
-- Note that no log file is actually generated, and outputs are lost if not run
-- with parameter -l or --log
function log(...)
    if LOG_ENABLED then
        print(...)
    end
end

-- Get size of lua dict. Factorio's version is implemented on the C++ side,
-- but this should be sufficient for our purposes
function table_size(t)
    local count = 0
    for _, _ in pairs(t) do
        count = count + 1
    end
    return count
end

-- keep track of all mods required in a particular session (do we need this?)
--required_in_session = {}
--paths_in_session = {}

-- Standardizes the lua require paths to standardized paths. Removes ".lua" from
-- the end, replaces all "." with "/", and changes "__modname__..." to
-- "./factorio-mods/modname/...". Does the same with "__base__" and "__core__",
-- except they point to "factorio-data" instead of "factorio-mods".
-- Also returns a boolean `absolute`, which indicates if the filepath is 
-- considered absolute (from the root mods directory) or local (relative to
-- CURRENT_FILE)
local function normalize_module_name(modname)
    -- remove lua from end if present
    modname = modname:gsub(".lua$", "")

    -- Normalize dots to paths, if appropriate
    -- First, check to see if there are any slashes in the path
    dot_path = modname:find("[/\\]") == nil
    -- If not, we assume it's a dot separated path, so we convert to forward
    -- slashes for consistency
    if dot_path then
        modname = modname:gsub("%.", "/")
    end
    -- We do this because some slash paths can have dots in their folder names
    -- that should not be converted to path delimeters (Krastorio2)

    -- Handle __mod-name__ format (alphanumeric + '-' + '_')
    local match, name = modname:match("(__([%w%-_]+)__)")
    --print(modname, match)

    local absolute = true
    if name == "core" or name == "base" then
        modname = string.gsub(modname, match, "./factorio-data/"..name)
    elseif match ~= nil then
        -- Check if the name is the name of a currently enabled mod
        -- We need to do this because some people like to name their files
        -- "__init__.lua" or similar (FactorioExtended-Plus-Logistics)
        if mods[name] then
            print(name)
            -- Change '-' to '%-' so the following gsub doesn't treat them
            -- as special characters
            local correct_match = string.gsub(match, "%-", "%%-")
            -- replace
            modname = string.gsub(modname, correct_match, "./factorio-mods/"..name)
        else
            -- Don't change modname and use relative paths
            absolute = false
        end
    else
        absolute = false
    end

    return modname, absolute
end

-- Overwrite of require function. Normalizes the module name to make it easier
-- to interpret later, and manages a number of other things. After preprocessing
-- has taken place, `old_require` is called and executed at the end of the
-- function.
local old_require = require
function require(module_name)
    --print("\tcurrent_file:", CURRENT_FILE)
    --print("\trequiring:", module_name)
    local absolute
    module_name, absolute = normalize_module_name(module_name)
    --print("Normalized module name:", module_name, absolute)
    --required_in_session[module_name] = true
    CURRENT_FILE = module_name

    --print(package.path)

    -- if not, try again after adding the path to the currently executing file
    --print("CURRENT_FILE:", CURRENT_FILE)

    local function get_parent(path)
        local pattern1 = "^(.+)/"
        local pattern2 = "^(.+)\\"

        if (string.match(path,pattern1) == nil) then
            return string.match(path,pattern2)
        else
            return string.match(path,pattern1)
        end
    end

    PARENT_DIR = get_parent(module_name)
    --print("PARENT_DIR:", PARENT_DIR)
    --print(paths_in_session[PARENT_DIR])
    local added = false
    if PARENT_DIR then
        local with_path = PARENT_DIR .. "/?.lua"
        -- add the mod directory to the path if it's an absolute path
        if not absolute then with_path = MOD_DIR .. "/" .. with_path end
        --print("\tWITH_PATH: " .. with_path)
        lua_add_path(with_path)
        --print("added path:", with_path)
        --paths_in_session[PARENT_DIR] = true
        added = true
    else -- God this whole thing is scuffed
        if not absolute then with_path = MOD_DIR .. CURRENT_DIR .. "/?.lua" end
        lua_add_path(with_path)
        added = true
    end

    result = old_require(module_name)

    if added then
        lua_remove_path()
    end

    return result
end

-- Menu simulations are not included in `factorio-data`; therefore we look for
-- this path when required and return the dummy values specified earlier above. 
-- This is done before all other searches, though after `normalize_module_name()`
local menu_simulations_searcher = function(module_name)
    if module_name == "./factorio-data/base/menu-simulations/menu-simulations" then
        return (function() return menu_simulations end)
    end
end


local archive_searcher = function(module_name)
    --print("Attempting to find " .. module_name .. " in python:")

    local contents, err = python_require(MOD_LIST, MOD, module_name, package.path)
    if contents then
        filepath = err
        CURRENT_DIR = filepath -- hacky patch
        return assert(load(contents, module_name))
    else
        return err
    end
end

-- First, the path is checked if its the menu simulations
table.insert(package.searchers, 1, menu_simulations_searcher)
-- Then, zip archives are prioritized more than file folders
table.insert(package.searchers, 2, archive_searcher)
-- Then the regular `reqiure` load process is followed, preloaded, files, etc.

-- =================
-- Interface Helpers
-- =================

-- Alter the package.path to include new directories to search through.
function lua_add_path(path)
    package.path = path .. ";" .. package.path
end

-- Remove the first path from package.path. Make sure not to remove system ones!
function lua_remove_path()
    pos = package.path:find(";") + 1
    package.path = package.path:sub(pos)
end

-- (Re)set the package path
function lua_set_path(path)
    package.path = path
end

-- Unloads all files. Lua has a package.preload functionality where files are
-- only included once and reused as necessary. This can cause problems when two
-- files have the exact same name however; If mod A has a file named "utils" and
-- is loaded first, mod B will require "utils" and will get A's copy of the file
-- instead of loading mod B's copy.
-- To prevent this, we unload all required files every time we load a stage,
-- which is excessive but guarantees correct behavior.
function lua_unload_cache()
    for k, _ in pairs(package.loaded) do
        package.loaded[k] = nil
    end
end