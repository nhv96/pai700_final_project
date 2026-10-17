# 1. What one training example looks like

One example is one window: the origin hour t (the last hour we know), and the target hour t + h that we want to predict.

- The answer (target): the real HtTot at t + h, in Wh.
- The question (features): a row of about 60 numbers, all known at the origin, except the measured future weather:
  - the HtTot of each of the last 24 hours, plus 2, 3, 4, 5, 6 and about 7 days back;
  - averages of HtTot over the last 6, 24 and 168 hours, and the spread over the last day;
  - the two seasonal-naive values ("same hour yesterday" and "same hour last week");
  - the weather now and its average over the last day;
  - the measured weather at the target hour and its average over the hours in between (the "perfect forecast");
  - the hour, weekday and month of the target hour.

There is no building ID, no year_of_construction and no floor_area. Trees need no scaling, so the values are raw (Wh, °C and so on).

# 2. What the model is

LightGBM builds a few hundred small decision trees, one after another.

- A decision tree asks a chain of yes/no questions, such as "is the heat used 24 hours ago above 80,000 Wh?" and "is the target hour before 06:00?". Each question splits the examples into two groups. The tree ends in leaves, and each leaf holds one predicted number.
- The first tree makes a rough prediction. The second tree is trained to fix the errors left over from the first. The third fixes the errors left after those two, and so on.
- The final prediction is the sum of all the trees' outputs, each scaled down by the learning rate (0.05), so that no single tree dominates.

The settings I used are 400 trees, each with at most 63 leaves. Each tree sees a random 80% of the rows and 80% of the columns, which reduces overfitting. A leaf must contain at least 100 examples, so the model can't memorize single hours.

# 3. The loss: what "fixing errors" means

The training goal is the absolute error (objective="l1"). It matches MAE and WAPE, the scores we report. The model is rewarded for being close on average, not for avoiding a few big misses. RMSE in kWh is still reported, but the model isn't trained for it.

# 4. Direct vs. residual target

I train two versions of the model:
- Direct: the trees learn the heat use itself.
- Residual: the trees learn actual minus seasonal-naive forecast, and I add the naive forecast back afterwards. The model then only has to learn the corrections, such as "colder than yesterday, so more heat".

Predictions are cut at 0, because heat use cannot be negative.

# 5. What is trained, and when

For each horizon (1, 6, 24 h) and each of the 10 folds, there is a separate training run:

1. Training set: all windows whose target hour is before the fold's validation start. In the first fold that is little data, and in the last fold it is almost everything up to 2021-09.
2. Validation set: windows whose target lies in the fold's 6-month block. The model has never seen them.
3. Pooled scheme: trained on all three buildings together, then scored on each building.
4. Leave-one-building-out scheme: trained on two buildings, then scored only on the third. This runs three times per fold, once for each building held out.

The model starts from scratch in every fold. Nothing is carried over.

# 6. What is kept fixed, and why there is no tuning yet

- The settings are the same in every fold and I did not adjust them while looking at the scores. No early stopping on the validation block either, because that would let validation data influence the model.
- The seasonal-naive lag (24 h or 168 h) is chosen per building on that building's windows before the fold. It only defines the baseline and the residual anchor.
- The final test block (from 2022-03-01) is not loaded at all. load_horizon drops every window whose target is on or after it.

# 7. Counting the work

3 horizons × 10 folds × 2 targets × (1 pooled + 3 leave-one-out) = 240 fits. That is why the run is slow.

# 8. What comes out

For every validation window, we store the actual value, the model's forecast and the baseline's forecast. score_table then computes MAE, RMSE, WAPE and skill per scheme, target, horizon, building, fold and season. The model is good if its skill is clearly above 0, which means a lower WAPE than the baseline.

Things to keep in mind

- The model is not tuned yet. If the trees look promising, we can tune the settings on the validation folds, never on the test block.
- Leave-one-out with only 3 buildings is weak evidence about new buildings in general.