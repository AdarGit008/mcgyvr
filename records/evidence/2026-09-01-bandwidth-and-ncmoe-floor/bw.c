#include <stdio.h>
#include <stdlib.h>
#include <omp.h>
int main(int argc,char**argv){
  long MB=atol(argv[1]); long N=MB*1024L*1024L/8;
  double *a=aligned_alloc(64,N*8); if(!a){printf("%5ld MB: ALLOC FAIL\n",MB);return 1;}
  double s=0,best=1e30;
  #pragma omp parallel for
  for(long i=0;i<N;i++) a[i]=i*1.0;
  for(int r=0;r<3;r++){ double t0=omp_get_wtime(),loc=0;
    #pragma omp parallel for reduction(+:loc)
    for(long i=0;i<N;i++) loc+=a[i];
    double t=omp_get_wtime()-t0; if(t<best)best=t; s+=loc; }
  printf("%5ld MB read: %6.1f GB/s  (threads=%d)\n",MB,(8.0*N/best)/1e9,omp_get_max_threads());
  free(a); return 0; }
