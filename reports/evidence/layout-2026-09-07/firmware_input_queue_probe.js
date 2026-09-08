// Compatibility entry: the input queue now shares the default-running clock gate.
require('../../../tools/pipeline/verify_firmware_clock.js')().catch(error=>{
  console.error(error);process.exitCode=1;
});
