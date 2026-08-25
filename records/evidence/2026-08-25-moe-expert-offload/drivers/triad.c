#include <stdio.h>
#include <stdlib.h>
#include <omp.h>
#define N 25000000L   /* 200 MB per array, 3 arrays = 600 MB */
static double a[N], b[N], c[N];
int main(int argc, char **argv){
  double s = (argc > 1) ? atof(argv[1]) : 3.0;   /* not a compile-time constant */
  double best = 1e30;
  #pragma omp parallel for
  for(long i=0;i<N;i++){ a[i]=1.0; b[i]=2.0; c[i]=0.5; }
  for(int r=0;r<5;r++){
    double t0=omp_get_wtime();
    #pragma omp parallel for
    for(long i=0;i<N;i++) a[i]=b[i]+s*c[i];
    double t=omp_get_wtime()-t0;
    if(t<best) best=t;
    s += 1e-12;                                   /* each rep differs */
  }
  double sum=0.0;
  #pragma omp parallel for reduction(+:sum)
  for(long i=0;i<N;i++) sum += a[i];              /* consume the result */
  printf("STREAM triad: %.1f GB/s  (threads=%d, best=%.4f s, checksum=%.3f)\n",
         (3.0*sizeof(double)*N/best)/1e9, omp_get_max_threads(), best, sum/N);
  return 0;
}
