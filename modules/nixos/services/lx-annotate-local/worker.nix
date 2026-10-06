# Typed internal worker record; see Workers.md.
# Keep host policy in config.nix and public options in options/runtime.nix.
{ lib }:
let
  inherit (lib) mkOption types;
  required = type: description: mkOption { inherit type description; };
  optional =
    type: default: description:
    mkOption { inherit type default description; };
  nonEmptyString = types.strMatching ".+";
  nullableString = types.nullOr nonEmptyString;
  poolType = types.submodule {
    options = {
      concurrency = required types.ints.positive "Number of worker child processes.";
      maxTasksPerChild = required types.ints.positive "Tasks before child recycling.";
      memoryHigh = required nonEmptyString "Systemd MemoryHigh.";
      memoryMax = required nonEmptyString "Systemd MemoryMax.";
      cpuQuota = required nonEmptyString "Systemd CPUQuota.";
      cpuWeight = required (types.ints.between 1 10000) "Systemd CPUWeight.";
      ioWeight = required (types.ints.between 1 10000) "Systemd IOWeight.";
      nice = required (types.ints.between (-20) 19) "Systemd Nice.";
      oomScoreAdjust = required (types.ints.between (-1000) 1000) "Systemd OOMScoreAdjust.";
    };
  };
  options = {
    unitName = required (types.strMatching "[a-zA-Z0-9_-]+") "Systemd unit name without suffix.";
    hostname = required nonEmptyString "Celery node prefix; renderer appends @%%h.";
    queues = required (types.listOf (types.strMatching "[a-zA-Z0-9_-]+")) "Nonempty list of queue names.";
    pool = required poolType "Resource and child-process policy.";
    mode = optional (types.enum [
      "always"
      "manual"
      "timer"
    ]) "always" "Activation policy.";
    environment = optional (types.attrsOf types.str) { } "Additional worker environment.";
    after = optional (types.listOf nonEmptyString) [ ] "Additional ordering dependencies.";
    wants = optional (types.listOf nonEmptyString) [ ] "Additional weak dependencies.";
    requires = optional (types.listOf nonEmptyString) [ ] "Additional required dependencies.";
    cudaVisibleDevices = optional nullableString null "Optional CUDA device selector.";
    taskSoftTimeLimitSeconds =
      optional (types.nullOr types.ints.positive) null
        "Optional soft task limit.";
    taskHardTimeLimitSeconds =
      optional (types.nullOr types.ints.positive) null
        "Optional hard task limit.";
    onCalendar = optional nullableString null "Systemd timer calendar.";
    randomizedDelaySec = optional nullableString null "Systemd timer jitter.";
    persistentTimer = optional (types.nullOr types.bool) null "Whether a missed timer catches up.";
    runtimeMaxSec = optional nullableString null "Optional service runtime bound.";
    timeoutStopSec = optional nullableString null "Optional warm-shutdown timeout.";
  };
in
input:
let
  worker =
    (lib.evalModules {
      modules = [
        {
          inherit options;
          config = input;
        }
      ];
    }).config;
  fail = message: throw "lx-annotate worker ${worker.unitName}: ${message}";
  valid =
    if worker.queues == [ ] then
      fail "queues must not be empty"
    else if lib.unique worker.queues != worker.queues then
      fail "queues must be unique"
    else if
      worker.mode == "timer"
      && (
        worker.onCalendar == null || worker.randomizedDelaySec == null || worker.persistentTimer == null
      )
    then
      fail "timer mode requires onCalendar, randomizedDelaySec and persistentTimer"
    else if
      worker.taskSoftTimeLimitSeconds != null
      && worker.taskHardTimeLimitSeconds != null
      && worker.taskSoftTimeLimitSeconds >= worker.taskHardTimeLimitSeconds
    then
      fail "soft task limit must be less than hard task limit"
    else
      true;
in
builtins.deepSeq worker (
  assert valid;
  {
    inherit (worker)
      unitName
      hostname
      queues
      mode
      environment
      after
      wants
      requires
      ;
    inherit (worker.pool) concurrency maxTasksPerChild;
    serviceConfig = {
      MemoryHigh = worker.pool.memoryHigh;
      MemoryMax = worker.pool.memoryMax;
      CPUQuota = worker.pool.cpuQuota;
      CPUWeight = worker.pool.cpuWeight;
      IOWeight = worker.pool.ioWeight;
      Nice = worker.pool.nice;
      OOMScoreAdjust = worker.pool.oomScoreAdjust;
    };
  }
  // lib.filterAttrs (_: value: value != null) {
    inherit (worker)
      cudaVisibleDevices
      taskSoftTimeLimitSeconds
      taskHardTimeLimitSeconds
      onCalendar
      randomizedDelaySec
      persistentTimer
      runtimeMaxSec
      timeoutStopSec
      ;
  }
)
