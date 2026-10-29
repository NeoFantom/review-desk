---
title: Estimating a Diffusion Constant from Short Trajectories
---

# Estimating a Diffusion Constant from Short Trajectories

## Abstract

We compare two estimators of the diffusion constant $D$ for trajectories shorter
than 100 steps. The covariance-based estimator is unbiased under localization noise,
while the mean-squared-displacement fit underestimates $D$ by up to 30 %.

## Method

For a one-dimensional random walk with step variance $2D\,\Delta t$ and
localization noise $\sigma$, the covariance estimator is

$$
\hat D = \frac{\overline{\Delta x^2}}{2\Delta t} + \frac{\overline{\Delta x_n \Delta x_{n+1}}}{\Delta t} \tag{1}
$$

- the first term is the naive estimate;
- the second term removes the noise contribution $\sigma^2$.

![Bias of both estimators versus trajectory length (synthetic data).](bias.png)

## Results

The mean-squared-displacement fit is biased low for trajectories shorter than
50 steps, whereas the covariance estimator stays within 2 % of the true value.
