#!/usr/bin/env runhaskell

{-
  command_distributor.hs

  Haskell rewrite of command_distributor.sh.
  - Validates inputs early (commands file exists, positive integers).
  - Requires SLURM_ARRAY_TASK_ID and checks it is in range.
  - Verifies GNU parallel is available before launching.
  - Streams the slice to parallel via stdin (no temp files needed).
  - Skips empty lines so blank commands are not submitted.
  - Returns a non-zero exit code if parallel fails.

  Usage:
    command_distributor.hs <commands_file> <num_batches> [jobs_per_batch]
    jobs_per_batch defaults to 40.
-}

import Control.Exception (catch, IOException)
import System.Environment (getArgs, lookupEnv)
import System.Exit (ExitCode (..), exitFailure, exitSuccess, exitWith)
import System.IO (Handle, hClose, hPutStrLn, stderr)
import System.Process
  ( CreateProcess (..)
  , StdStream (CreatePipe)
  , createProcess
  , proc
  , waitForProcess
  , std_in
  )

import Text.Read (readMaybe)
import System.Directory (doesFileExist, findExecutable)

data Options = Options
  { optFile :: FilePath
  , optBatches :: Int
  , optJobs :: Int
  , optTaskId :: Int
  }

main :: IO ()
main = do
  args <- getArgs
  opts <- parseArgs args >>= validateInputs
  ensureParallelAvailable

  contents <- readFile (optFile opts)
  let commands = filter (not . null) (lines contents)
      total = length commands
  if total == 0
    then die "Commands file is empty after removing blank lines."
    else pure ()

  let slice = computeSlice (optTaskId opts) (optBatches opts) commands
  if null slice
    then do
      putStrLn $ "No commands to execute for batch " ++ show (optTaskId opts) ++ "."
      exitSuccess
    else pure ()

  putStrLn $
    "Executing batch "
      ++ show (optTaskId opts)
      ++ ": "
      ++ show (length slice)
      ++ " commands with "
      ++ show (optJobs opts)
      ++ " concurrent jobs."

  runParallel (optJobs opts) slice

parseArgs :: [String] -> IO Options
parseArgs [file, batchesStr] = do
  batches <- parsePositive "number_of_batches" batchesStr
  taskId <- requireTaskId
  pure $ Options file batches 40 taskId
parseArgs [file, batchesStr, jobsStr] = do
  batches <- parsePositive "number_of_batches" batchesStr
  jobs <- parsePositive "jobs_per_batch" jobsStr
  taskId <- requireTaskId
  pure $ Options file batches jobs taskId
parseArgs _ = do
  hPutStrLn stderr usage
  exitFailure

validateInputs :: Options -> IO Options
validateInputs opts = do
  exists <- fileExists (optFile opts)
  if not exists
    then die $ "Commands file does not exist: " ++ optFile opts
    else pure ()
  whenOutOfRange (optTaskId opts) (optBatches opts)
  pure opts

requireTaskId :: IO Int
requireTaskId = do
  env <- lookupEnv "SLURM_ARRAY_TASK_ID"
  case env >>= readMaybe of
    Just n | n > 0 -> pure n
    _ -> die "SLURM_ARRAY_TASK_ID is not set or not a positive integer."

parsePositive :: String -> String -> IO Int
parsePositive label s =
  case readMaybe s of
    Just n | n > 0 -> pure n
    _ -> die $ label ++ " must be a positive integer."

whenOutOfRange :: Int -> Int -> IO ()
whenOutOfRange task total =
  if task < 1 || task > total
    then die $
      "SLURM_ARRAY_TASK_ID (" ++ show task ++ ") is out of range (1-" ++ show total ++ ")."
    else pure ()

computeSlice :: Int -> Int -> [a] -> [a]
computeSlice taskIdx batches xs =
  let total = length xs
      perBatch = ceiling (fromIntegral total / fromIntegral batches :: Double)
      startIdx = (taskIdx - 1) * perBatch
      endIdx = min total (taskIdx * perBatch)
   in take (endIdx - startIdx) (drop startIdx xs)

runParallel :: Int -> [String] -> IO ()
runParallel jobs cmds = do
  let p =
        (proc "parallel" ["--jobs", show jobs])
          { std_in = CreatePipe
          }
  (mIn, _, _, ph) <- createProcess p
  case mIn of
    Nothing -> die "Failed to open stdin for parallel."
    Just h -> do
      mapM_ (\c -> hPutStrLn h c) cmds
      hCloseSafe h
  code <- waitForProcess ph
  case code of
    ExitSuccess -> pure ()
    ExitFailure n -> exitWith (ExitFailure n)

ensureParallelAvailable :: IO ()
ensureParallelAvailable = do
  m <- findExecutable "parallel"
  case m of
    Just _ -> pure ()
    Nothing -> die "GNU parallel is required but was not found in PATH."

fileExists :: FilePath -> IO Bool
fileExists path =
  doesFileExist path `catch` (\(_ :: IOException) -> pure False)

hCloseSafe :: Handle -> IO ()
hCloseSafe h = hClose h `catch` (\(_ :: IOException) -> pure ())

die :: String -> IO a
die msg = hPutStrLn stderr ("Error: " ++ msg) >> exitFailure

usage :: String
usage =
  "Usage: command_distributor.hs <commands_file> <number_of_batches> [jobs_per_batch]\n"
    ++ "Example: command_distributor.hs cmds.txt 4 20\n"
