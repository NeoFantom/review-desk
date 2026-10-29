# Decision letter (synthetic example)

All names, comments and the paper are invented for this demo.

## Reviewer 1

Comment 1: The abstract claims the energy error stays below 1e-6 "over 10^5 periods",
but the main text never states which energy is meant. Is it the physical energy or
some corrected quantity?
@anchor: keeps the energy error below $10^{-6}$ over $10^{5}$ periods

Comment 2: The splitting in Eq. (2) is presented without saying why the dissipative
flow should be applied in two half steps. A sentence of motivation would help.
@anchor: \Phi_{\dt} &= \varphi^{D}_{\dt/2}

Comment 3: "at equal cost" is vague. Do you mean equal wall-clock time or equal
number of force evaluations? This matters for the factor of forty.

Comment 4: The comparison is only against RK4. A comparison with a standard
symplectic method that ignores damping would show whether the exact treatment of
the dissipation is what helps.
@anchor: compares the scheme with a fourth-order Runge--Kutta method (RK4)

## Reviewer 2

Comment 1: The phrase "the shaded band marks the round-off floor" in the figure
caption is unclear: how was this floor estimated?
@anchor: The shaded band marks the round-off floor.

Comment 2: The claim that the phase-error slope is smaller "by a factor of three"
is not supported by a figure or table.
@anchor: the splitting scheme has a smaller slope by a factor of three

Comment 3: In the conclusion, "Langevin dynamics without noise" is just damped
Hamiltonian dynamics; the sentence suggests more generality than is shown.
@anchor: such as Langevin dynamics with zero noise
