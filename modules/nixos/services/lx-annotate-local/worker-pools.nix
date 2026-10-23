{
  lib,
  includeHubTransfer ? false,
}:
let
  inherit (lib) mkOption types;
  workerPoolType = types.submodule {
    options = {
      concurrency = mkOption {
        type = types.ints.positive;
        default = 1;
        description = "Celery worker concurrency for this workload pool.";
      };
      maxTasksPerChild = mkOption {
        type = types.ints.positive;
        default = 1;
        description = "Maximum Celery tasks each child process handles before recycling.";
      };
      memoryHigh = mkOption {
        type = types.str;
        default = "1G";
        description = "MemoryHigh limit applied to this Celery workload pool.";
      };
      memoryMax = mkOption {
        type = types.str;
        default = "2G";
        description = "MemoryMax limit applied to this Celery workload pool.";
      };
      cpuQuota = mkOption {
        type = types.str;
        default = "35%";
        description = "CPUQuota assigned to this Celery workload pool.";
      };
      cpuWeight = mkOption {
        type = types.ints.between 1 10000;
        default = 100;
        description = "CPUWeight assigned to this Celery workload pool.";
      };
      ioWeight = mkOption {
        type = types.ints.between 1 10000;
        default = 100;
        description = "IOWeight assigned to this Celery workload pool.";
      };
      nice = mkOption {
        type = types.int;
        default = 15;
        description = "Systemd Nice value for this Celery workload pool.";
      };
      oomScoreAdjust = mkOption {
        type = types.int;
        default = 750;
        description = "OOMScoreAdjust value for this Celery workload pool.";
      };
    };
  };
in
mkOption {
  type = types.submodule {
    options = {
      pipeline = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 1;
          memoryHigh = "2G";
          memoryMax = "4G";
          cpuQuota = "45%";
          nice = 16;
          oomScoreAdjust = 800;
        };
        description = "Celery pool for upload/import/anonymization pipeline work.";
      };
      ffmpeg = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 1;
          memoryHigh = "10G";
          memoryMax = "12G";
          cpuQuota = "600%";
          cpuWeight = 100;
          ioWeight = 100;
          nice = 0;
          oomScoreAdjust = 850;
        };
        description = "Celery pool for bounded FFmpeg media reprocessing.";
      };
      frameExtraction = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 1;
          memoryHigh = "3G";
          memoryMax = "5G";
          cpuQuota = "55%";
          nice = 18;
          oomScoreAdjust = 850;
        };
        description = "Celery pool for FFmpeg frame extraction and post-validation rebuilds.";
      };
      inference = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 1;
          memoryHigh = "12G";
          memoryMax = "16G";
          cpuQuota = "250%";
          nice = 10;
          oomScoreAdjust = 350;
        };
        description = "Celery pool for AI temporal inference jobs.";
      };
      training = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 1;
          memoryHigh = "24G";
          memoryMax = "32G";
          cpuQuota = "400%";
          nice = 5;
          oomScoreAdjust = 200;
        };
        description = "Celery pool for single-GPU model training jobs.";
      };
      llmInference = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 1;
          memoryHigh = "4G";
          memoryMax = "8G";
          cpuQuota = "150%";
          nice = 12;
          oomScoreAdjust = 350;
        };
        description = "Celery pool for Ollama-backed report and metadata LLM inference jobs.";
      };
      maintenance = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 100;
          memoryHigh = "1G";
          memoryMax = "2G";
          cpuQuota = "25%";
          nice = 12;
          oomScoreAdjust = 700;
        };
        description = "Celery pool for default and maintenance queues.";
      };
    }
    // lib.optionalAttrs includeHubTransfer {
      hubTransfer = mkOption {
        type = workerPoolType;
        default = {
          concurrency = 1;
          maxTasksPerChild = 20;
          memoryHigh = "768M";
          memoryMax = "1536M";
          cpuQuota = "35%";
          nice = 14;
          oomScoreAdjust = 750;
        };
        description = "Celery pool dedicated to bounded outbound hub transfer and recovery jobs.";
      };
    };
  };
  default = { };
  description = "Queue-specific Celery worker pools for load-balancing heavy media jobs.";
}
