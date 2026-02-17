// Implementation of C Testing Coverage Tool runtime library
// Provides coverage data collection and JSON output generation

#include "cov_runtime.h"    
#include <stdio.h> 
#include <inttypes.h>         

// Global array that stores hit counts
uint64_t branch_counters[MAX_BRANCHES] = {0};

// dump_coverage() - Writes coverage data to coverage.json file
__attribute__((destructor))
void dump_coverage(void){
    //Open coverage.json for writing
    FILE* f = fopen("coverage.json", "w");

    // Check if file opened successfully
    if(!f){
        fprintf(stderr, "Error: Could not create coverage.json\n");
        return;
    }

    // Write JSON header
    fprintf(f, "{\n \"branches\": [\n");

    // Track the first entry
    int first = 1;

    //Iterate through all branch counters
    for(int i = 0; i < MAX_BRANCHES; i+= 2) {
        // Detect hited branches
        if(branch_counters[i] > 0 || branch_counters[i+1] > 0) {
            // Add comma before entry (not first)
            if (!first) {
                fprintf(f, ",\n");
            }

            // Write branch data
            fprintf(f, "    {\"id\": %d, \"true\": %" PRIu64 ", \"false\": %" PRIu64 "}",
                i / 2,                  // Branch ID (2 counters per branch)
                branch_counters[i],     // True hits
                branch_counters[i + 1]  // False hits
            );

            first = 0;
        }
    }

    //Close the file
    fprintf(f, "\n ]\n}\n");
    fclose(f);
    fprintf(stderr, "[Coverage] Wrote coverage data to coverage.json\n");
}