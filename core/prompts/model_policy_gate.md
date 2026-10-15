# Model Policy Gate Prompt Fragment

Read phase model policy and actual configured runner readback before phase work.
The shared runtime requires the exact required model and at least its reasoning
floor. Higher reasoning is sufficient. Missing, different or insufficient
readback stops ordinary delivery; authorized repairs apply to the next run.
Terminal handling precedes this gate.
