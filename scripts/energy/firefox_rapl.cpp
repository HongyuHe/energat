// Adapted from: https://github.com/mozilla/newtab-dev/tree/master/tools

#include <assert.h>
#include <getopt.h>
#include <math.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

#include <algorithm>
#include <numeric>
#include <vector>

// The value of argv[0] passed to main(). Used in error messages.
static const char *gArgv0;

static void
Abort(const char *aFormat, ...)
{
  va_list vargs;
  va_start(vargs, aFormat);
  fprintf(stderr, "%s: ", gArgv0);
  vfprintf(stderr, aFormat, vargs);
  fprintf(stderr, "\n");
  va_end(vargs);

  exit(1);
}

static void
CmdLineAbort(const char *aMsg)
{
  if (aMsg)
  {
    fprintf(stderr, "%s: %s\n", gArgv0, aMsg);
  }
  fprintf(stderr, "Use --help for more information.\n");
  exit(1);
}

// A special value that represents an estimate from an unsupported RAPL domain.
static const double kUnsupported_j = -1.0;

// Print to stdout and flush it, so that the output appears immediately even if
// being redirected through |tee| or anything like that.
static void
PrintAndFlush(const char *aFormat, ...)
{
  va_list vargs;
  va_start(vargs, aFormat);
  vfprintf(stdout, aFormat, vargs);
  va_end(vargs);

  fflush(stdout);
}

//---------------------------------------------------------------------------
// Linux-specific code
//---------------------------------------------------------------------------

#include <linux/perf_event.h>
#include <sys/syscall.h>

// There is no glibc wrapper for this system call so we provide our own.
static int
perf_event_open(struct perf_event_attr *aAttr, pid_t aPid, int aCpu,
                int aGroupFd, unsigned long aFlags)
{
  return syscall(__NR_perf_event_open, aAttr, aPid, aCpu, aGroupFd, aFlags);
}

// Returns false if the file cannot be opened.
template <typename T>
static bool
ReadValueFromPowerFile(const char *aStr1, const char *aStr2, const char *aStr3,
                       const char *aScanfString, T *aOut)
{
  // The filenames going into this buffer are under our control and the longest
  // one is "/sys/bus/event_source/devices/power/events/energy-cores.scale".
  // So 256 chars is plenty.
  char filename[256];

  sprintf(filename, "/sys/bus/event_source/devices/power/%s%s%s",
          aStr1, aStr2, aStr3);
  FILE *fp = fopen(filename, "r");
  if (!fp)
  {
    return false;
  }
  if (fscanf(fp, aScanfString, aOut) != 1)
  {
    Abort("fscanf() failed");
  }
  fclose(fp);

  return true;
}

// This class encapsulates the reading of a single RAPL domain.
class Domain
{
  bool mIsSupported; // Is the domain supported by the processor?

  // These three are only set if |mIsSupported| is true.
  double mJoulesPerTick; // How many Joules each tick of the MSR represents.
  int mFd;               // The fd through which the MSR is read.
  double mPrevTicks;     // The previous sample's MSR value.

public:
  enum IsOptional
  {
    Optional,
    NonOptional
  };

  Domain(const char *aName, uint32_t aType, IsOptional aOptional = NonOptional)
  {
    uint64_t config;
    if (!ReadValueFromPowerFile("events/energy-", aName, "", "event=%llx",
                                &config))
    {
      // Failure is allowed for optional domains.
      if (aOptional == NonOptional)
      {
        Abort("failed to open file for non-optional domain '%s'\n"
              "- Is your kernel version 3.14 or later, as required? "
              "Run |uname -r| to see.",
              aName);
      }
      mIsSupported = false;
      return;
    }

    mIsSupported = true;

    ReadValueFromPowerFile("events/energy-", aName, ".scale", "%lf",
                           &mJoulesPerTick);

    // The unit should be "Joules", so 128 chars should be plenty.
    char unit[128];
    ReadValueFromPowerFile("events/energy-", aName, ".unit", "%127s", unit);
    if (strcmp(unit, "Joules") != 0)
    {
      Abort("unexpected unit '%s' in .unit file", unit);
    }

    struct perf_event_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.type = aType;
    attr.size = uint32_t(sizeof(attr));
    attr.config = config;

    // Measure all processes/threads. The specified CPU doesn't matter.
    mFd = perf_event_open(&attr, /* pid = */ -1, /* cpu = */ -1,
                          /* group_fd = */ -1, /* flags = */ 0);
    if (mFd < 0)
    {
      Abort("perf_event_open() failed\n"
            "- Did you run as root (e.g. with |sudo|) or set\n"
            "  /proc/sys/kernel/perf_event_paranoid to 0, as required?");
    }

    mPrevTicks = 0;
  }

  ~Domain()
  {
    if (mIsSupported)
    {
      close(mFd);
    }
  }

  double EnergyEstimate()
  {
    if (!mIsSupported)
    {
      return kUnsupported_j;
    }

    uint64_t thisTicks;
    if (read(mFd, &thisTicks, sizeof(uint64_t)) != sizeof(uint64_t))
    {
      Abort("read() failed");
    }

    uint64_t ticks = thisTicks - mPrevTicks;
    mPrevTicks = thisTicks;
    double joules = ticks * mJoulesPerTick;
    return joules;
  }
};

class RAPL
{
  Domain *mPkg;
  Domain *mCores;
  Domain *mGpu;
  Domain *mRam;

public:
  RAPL()
  {
    uint32_t type;
    ReadValueFromPowerFile("type", "", "", "%u", &type);

    mPkg = new Domain("pkg", type);
    mCores = new Domain("cores", type, Domain::Optional);
    mGpu = new Domain("gpu", type, Domain::Optional);
    mRam = new Domain("ram", type, Domain::Optional);
    if (!mPkg || !mCores || !mGpu || !mRam)
    {
      Abort("new Domain() failed");
    }
  }

  ~RAPL()
  {
    delete mPkg;
    delete mCores;
    delete mGpu;
    delete mRam;
  }

  void EnergyEstimates(double &aPkg_J, double &aCores_J, double &aGpu_J,
                       double &aRam_J)
  {
    aPkg_J = mPkg->EnergyEstimate();
    aCores_J = mCores->EnergyEstimate();
    aGpu_J = mGpu->EnergyEstimate();
    aRam_J = mRam->EnergyEstimate();
  }
};

//---------------------------------------------------------------------------
// The main loop
//---------------------------------------------------------------------------

// The sample interval, measured in seconds.
static double gSampleInterval_sec;

// The platform-specific RAPL-reading machinery.
static RAPL *gRapl;

// All the sampled "total" values, in Watts.
static std::vector<double> gTotals_W;

// Power = Energy / Time, where power is measured in Watts, Energy is measured
// in Joules, and Time is measured in seconds.
static double
JoulesToWatts(double aJoules)
{
  return aJoules / gSampleInterval_sec;
}

// "Normalize" here means convert kUnsupported_j to zero so it can be used in
// additive expressions. All printed values are 5 or maybe 6 chars (though 6
// chars would require a value > 100 W, which is unlikely).
static void
NormalizeAndPrintAsWatts(char *aBuf, double &aValue_J)
{
  if (aValue_J == kUnsupported_j)
  {
    aValue_J = 0;
    sprintf(aBuf, "%s", " n/a ");
  }
  else
  {
    sprintf(aBuf, "%5.2f", JoulesToWatts(aValue_J));
  }
}

static void
SigAlrmHandler(int aSigNum, siginfo_t *aInfo, void *aContext)
{
  static int sampleNumber = 1;

  double pkg_J, cores_J, gpu_J, ram_J;
  gRapl->EnergyEstimates(pkg_J, cores_J, gpu_J, ram_J);

  // We should have pkg and cores estimates, but might not have gpu and ram
  // estimates.
  assert(pkg_J != kUnsupported_j);
  //   assert(cores_J != kUnsupported_j);

  // This needs to be big enough to print watt values to two decimal places. 16
  // should be plenty.
  static const size_t kNumStrLen = 16;

  static char pkgStr[kNumStrLen], coresStr[kNumStrLen], gpuStr[kNumStrLen],
      ramStr[kNumStrLen];
  NormalizeAndPrintAsWatts(pkgStr, pkg_J);
  NormalizeAndPrintAsWatts(coresStr, cores_J);
  NormalizeAndPrintAsWatts(gpuStr, gpu_J);
  NormalizeAndPrintAsWatts(ramStr, ram_J);

  // Core and GPU power are a subset of the package power.
  assert(pkg_J >= cores_J + gpu_J);

  // Compute "other" (i.e. rest of the package) and "total" only after the
  // other values have been normalized.

  char otherStr[kNumStrLen];
  double other_J = pkg_J - cores_J - gpu_J;
  NormalizeAndPrintAsWatts(otherStr, other_J);

  char totalStr[kNumStrLen];
  double total_J = pkg_J + ram_J;
  NormalizeAndPrintAsWatts(totalStr, total_J);

  // gTotals_W.push_back(JoulesToWatts(total_J));
  gTotals_W.push_back(total_J);

  // Print and flush so that the output appears immediately even if being
  // redirected through |tee| or anything like that.
  PrintAndFlush("#%02d %s W = %s (%s + %s + %s) + %s W\n",
                sampleNumber++, totalStr, pkgStr, coresStr, gpuStr, otherStr,
                ramStr);
}

static void
Finish()
{
  size_t n = gTotals_W.size();

  // This time calculation assumes that the timers are perfectly accurate which
  // is not true but the inaccuracy should be small in practice.
  double time = n * gSampleInterval_sec;

  printf("\n");
  printf("%d sample%s taken over a period of %.3f second%s\n",
         int(n), n == 1 ? "" : "s",
         n * gSampleInterval_sec, time == 1.0 ? "" : "s");

  if (n == 0 || n == 1)
  {
    exit(0);
  }

  // Compute the mean.
  double sum = std::accumulate(gTotals_W.begin(), gTotals_W.end(), 0.0);
  double mean = sum / n;

  printf("Total energy: %f Joules\n", sum);

  // Compute the *population* standard deviation:
  //
  //   popStdDev = sqrt(Sigma(x - m)^2 / n)
  //
  // where |x| is the sum variable, |m| is the mean, and |n| is the
  // population size.
  //
  // This is different from the *sample* standard deviation, which divides by
  // |n - 1|, and would be appropriate if we were using a random sample of a
  // larger population.
  double sumOfSquaredDeviations = 0;
  for (auto iter = gTotals_W.begin(); iter != gTotals_W.end(); ++iter)
  {
    double deviation = (*iter - mean);
    sumOfSquaredDeviations += deviation * deviation;
  }
  double popStdDev = sqrt(sumOfSquaredDeviations / n);

  // Sort so that percentiles can be determined. We use the "Nearest Rank"
  // method of determining percentiles, which is simplest to compute and which
  // chooses values from those that appear in the input set.
  std::sort(gTotals_W.begin(), gTotals_W.end());

  // printf("\n");
  // printf("Distribution of 'total' values:\n");
  // printf("            mean = %5.2f W\n", mean);
  // printf("         std dev = %5.2f W\n", popStdDev);
  // printf("  0th percentile = %5.2f W (min)\n", gTotals_W[0]);
  // printf("  5th percentile = %5.2f W\n", gTotals_W[ceil(0.05 * n) - 1]);
  // printf(" 25th percentile = %5.2f W\n", gTotals_W[ceil(0.25 * n) - 1]);
  // printf(" 50th percentile = %5.2f W\n", gTotals_W[ceil(0.50 * n) - 1]);
  // printf(" 75th percentile = %5.2f W\n", gTotals_W[ceil(0.75 * n) - 1]);
  // printf(" 95th percentile = %5.2f W\n", gTotals_W[ceil(0.95 * n) - 1]);
  // printf("100th percentile = %5.2f W (max)\n", gTotals_W[n - 1]);

  exit(0);
}

static void
SigIntHandler(int aSigNum, siginfo_t *aInfo, void *aContext)
{
  Finish();
}

static void
PrintUsage()
{
  printf(
      "usage: rapl [options]\n"
      "\n"
      "Options:\n"
      "\n"
      "  -h --help                 show this message\n"
      "  -i --sample-interval <N>  sample every N ms [default=1000]\n"
      "  -n --sample-count <N>     get N samples (0 means unlimited) [default=0]\n"
      "\n"
      "On Linux this program can only be run by the super-user unless the contents\n"
      "of /proc/sys/kernel/perf_event_paranoid is set to 0 or lower.\n"
      "\n");
}

int main(int argc, char **argv)
{
  // Process command line options.

  gArgv0 = argv[0];

  // Default values.
  int sampleInterval_msec = 1000;
  int sampleCount = 0;

  struct option longOptions[] = {
      {"help", no_argument, NULL, 'h'},
      {"sample-interval", required_argument, NULL, 'i'},
      {"sample-count", required_argument, NULL, 'n'},
      {NULL, 0, NULL, 0}};
  const char *shortOptions = "hi:n:";

  int c;
  char *endPtr;
  while ((c = getopt_long(argc, argv, shortOptions, longOptions, NULL)) != -1)
  {
    switch (c)
    {
    case 'h':
      PrintUsage();
      exit(0);

    case 'i':
      sampleInterval_msec = strtol(optarg, &endPtr, /* base = */ 10);
      if (*endPtr)
      {
        CmdLineAbort("sample interval is not an integer");
      }
      if (sampleInterval_msec < 1 || sampleInterval_msec > 3600000)
      {
        CmdLineAbort("sample interval must be in the range 1..3600000 ms");
      }
      break;

    case 'n':
      sampleCount = strtol(optarg, &endPtr, /* base = */ 10);
      if (*endPtr)
      {
        CmdLineAbort("sample count is not an integer");
      }
      if (sampleCount < 0 || sampleCount > 1000000)
      {
        CmdLineAbort("sample count must be in the range 0..1000000");
      }
      break;

    default:
      CmdLineAbort(NULL);
    }
  }

  // The RAPL MSRs update every ~1 ms, but the measurement period isn't exactly
  // 1 ms, which means the sample periods are not exact. "Power Measurement
  // Techniques on Standard Compute Nodes: A Quantitative Comparison" by
  // Hackenberg et al. suggests the following.
  //
  //   "RAPL provides energy (and not power) consumption data without
  //   timestamps associated to each counter update. This makes sampling rates
  //   above 20 Samples/s unfeasible if the systematic error should be below
  //   5%... Constantly polling the RAPL registers will both occupy a processor
  //   core and distort the measurement itself."
  //
  // So warn about this case.
  if (sampleInterval_msec < 50)
  {
    fprintf(stderr,
            "\nWARNING: sample intervals < 50 ms are likely to produce "
            "inaccurate estimates\n\n");
  }
  gSampleInterval_sec = double(sampleInterval_msec) / 1000;

  // Initialize the platform-specific RAPL reading machinery.
  gRapl = new RAPL();
  if (!gRapl)
  {
    Abort("new RAPL() failed");
  }

  // Install the signal handlers.

  struct sigaction sa;
  memset(&sa, 0, sizeof(sa));
  sa.sa_flags = SA_RESTART | SA_SIGINFO;
  // The extra parens around (0) suppress a -Wunreachable-code warning on OS X
  // where sigemptyset() is a macro that can never fail and always returns 0.
  if (sigemptyset(&sa.sa_mask) < (0))
  {
    Abort("sigemptyset() failed");
  }
  sa.sa_sigaction = SigAlrmHandler;
  if (sigaction(SIGALRM, &sa, NULL) < 0)
  {
    Abort("sigaction(SIGALRM) failed");
  }
  sa.sa_sigaction = SigIntHandler;
  if (sigaction(SIGINT, &sa, NULL) < 0)
  {
    Abort("sigaction(SIGINT) failed");
  }

  // Set up the timer.
  struct itimerval timer;
  timer.it_interval.tv_sec = sampleInterval_msec / 1000;
  timer.it_interval.tv_usec = (sampleInterval_msec % 1000) * 1000;
  timer.it_value = timer.it_interval;
  if (setitimer(ITIMER_REAL, &timer, NULL) < 0)
  {
    Abort("setitimer() failed");
  }

  // Print header.
  PrintAndFlush("    total W = _pkg_ (cores + _gpu_ + other) + _ram_ W\n");

  // Take samples.
  if (sampleCount == 0)
  {
    while (true)
    {
      pause();
    }
  }
  else
  {
    for (int i = 0; i < sampleCount; i++)
    {
      pause();
    }
  }

  Finish();

  return 0;
}