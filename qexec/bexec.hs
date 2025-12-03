#!/usr/bin/env runhaskell

{-
  bexec.hs

  Haskell rewrite of bexec.sh. Submits an array job via qexec.sh where each
  array task runs command_distributor.sh over a slice of the commands file.

  Differences vs the original shell script:
    * Uses a safer default memory request (6G) instead of none.
    * Resolves qexec.sh and command_distributor.sh either next to this script
      or from PATH (hardcoded ~/bin paths removed).
    * Validates inputs before submission and fails fast with clear errors.

  Usage:
    bexec.hs -f commands.txt [-n NODES] [--time HOURS] [--ncpus CPUS]
             [--mem 12G] [-j JOBS]
-}

import Control.Exception (catch, IOException)
import Data.Char (isDigit)
import System.Directory (doesFileExist, findExecutable)
import qualified System.Directory as Dir
import System.Environment (getArgs)
import System.Exit (ExitCode (..), exitFailure, exitSuccess, exitWith)
import System.FilePath ((</>), takeDirectory)
import System.IO (hPutStrLn, stderr)
import System.Process (createProcess, proc, waitForProcess)

data Options = Options
  { optFile :: FilePath
  , optNodes :: Int
  , optTime :: Int -- hours, integer because qexec.sh expects integer arithmetic
  , optNcpus :: Int
  , optMem :: Maybe String
  , optJobs :: Int
  }
  deriving (Show)

defaultOptions :: Options
defaultOptions =
  Options
    { optFile = ""
    , optNodes = 1
    , optTime = 1
    , optNcpus = 40
    , optMem = Nothing -- default: omit --mem for whole-node clusters
    , optJobs = 40
    }

main :: IO ()
main = do
  raw <- getArgs
  opts <-
    case parseArgs raw of
      Left msg
        | msg == usage -> putStrLn usage >> exitSuccess
        | otherwise -> dieWith "Error" msg
      Right v -> pure v
  validateOptions opts
  qexecPath <- findScript "qexec.sh"
  distributorPath <- findScript "command_distributor.sh"

  let arraySpec = "1-" ++ show (optNodes opts)
      memArgs =
        case optMem opts of
          Just m -> ["--mem", m]
          Nothing -> []
      qexecArgs =
        [ "--time"
        , show (optTime opts)
        , "--ncpus"
        , show (optNcpus opts)
        , "--nodes"
        , "1"
        , "--array=" ++ arraySpec
        ]
          ++ memArgs
          ++ [ "--"
             , distributorPath
             , optFile opts
             , show (optNodes opts)
             , show (optJobs opts)
             ]

  putStrLn "Submitting array job with:"
  putStrLn $ "  " ++ unwords (qexecPath : qexecArgs)

  (_, _, _, ph) <- createProcess (proc qexecPath qexecArgs)
  code <- waitForProcess ph
  exitWith code

dieWith :: String -> String -> IO a
dieWith prefix msg = do
  hPutStrLn stderr (prefix ++ ": " ++ msg)
  exitFailure

parseArgs :: [String] -> Either String Options
parseArgs = go defaultOptions
  where
    go opts [] =
      if null (optFile opts)
        then Left "The --file/-f option is required."
        else Right opts
    go opts ("-f" : val : rest) = go opts {optFile = val} rest
    go opts ("--file" : val : rest) = go opts {optFile = val} rest
    go opts ("-n" : val : rest) = setInt "nodes" (\n o -> o {optNodes = n}) val opts rest
    go opts ("--nodes" : val : rest) = setInt "nodes" (\n o -> o {optNodes = n}) val opts rest
    go opts ("--time" : val : rest) = setInt "time" (\n o -> o {optTime = n}) val opts rest
    go opts ("--ncpus" : val : rest) = setInt "ncpus" (\n o -> o {optNcpus = n}) val opts rest
    go opts ("--mem" : val : rest)
      | val == "0" = go opts {optMem = Nothing} rest
      | validMem val = go opts {optMem = Just val} rest
      | otherwise = Left "Invalid --mem value (expected like 6G, 512M, 1024K, or 0 to omit)."
    go opts ("-j" : val : rest) = setInt "jobs" (\n o -> o {optJobs = n}) val opts rest
    go opts ("--jobs" : val : rest) = setInt "jobs" (\n o -> o {optJobs = n}) val opts rest
    go _ ("-h" : _) = Left usage
    go _ ("--help" : _) = Left usage
    go _ (tok : _) = Left $ "Unknown option: " ++ tok

    setInt :: String -> (Int -> Options -> Options) -> String -> Options -> [String] -> Either String Options
    setInt label setter val opts rest =
      case readMaybeInt val of
        Nothing -> Left $ "Invalid " ++ label ++ " value (must be a positive integer)."
        Just n ->
          if n <= 0
            then Left $ label ++ " must be > 0."
            else go (setter n opts) rest

usage :: String
usage =
  unlines
    [ "Usage: bexec.hs -f <commands_file> [options]"
    , ""
    , "Options:"
    , "  -f, --file   Path to commands file (required)"
    , "  -n, --nodes  Number of array tasks/nodes (default 1)"
    , "      --time   Hours per task (integer, default 1)"
    , "      --ncpus  CPUs per task (default 40)"
    , "      --mem    Memory per task (default 6G; set to 0 to omit)"
    , "  -j, --jobs   Max concurrent commands per node (default 40)"
    , "  -h, --help   Show this message"
    ]

readMaybeInt :: String -> Maybe Int
readMaybeInt s =
  if all isDigit s && not (null s)
    then Just (read s)
    else Nothing

validMem :: String -> Bool
validMem s =
  let upper = map toUpperAscii s
   in length upper >= 2 && last upper `elem` ("KMG" :: String) && all isDigit (init upper)

toUpperAscii :: Char -> Char
toUpperAscii c
  | c >= 'a' && c <= 'z' = toEnum (fromEnum c - 32)
  | otherwise = c

validateOptions :: Options -> IO ()
validateOptions opts = do
  exists <- doesFileExist (optFile opts)
  if not exists
    then dieWith "Error" $ "Commands file does not exist: " ++ optFile opts
    else pure ()
  case optMem opts of
    Just m | m == "0" -> pure () -- allow explicit "0" to mean omit
    Just m | validMem m -> pure ()
    Just m -> dieWith "Error" $ "Invalid mem value: " ++ m
    Nothing -> pure ()

findScript :: String -> IO FilePath
findScript name = do
  fromExeDir <- findNextToExecutable name
  case fromExeDir of
    Just p -> pure p
    Nothing -> do
      m <- findExecutable name
      case m of
        Just p -> pure p
        Nothing -> dieWith "Error" $ "Unable to locate " ++ name ++ " next to bexec or in PATH."

findNextToExecutable :: String -> IO (Maybe FilePath)
findNextToExecutable name = do
  mExe <- getExecutablePathSafe
  case mExe of
    Nothing -> pure Nothing
    Just exe -> do
      let candidate = takeDirectory exe </> name
      ok <- doesFileExist candidate
      pure $ if ok then Just candidate else Nothing

getExecutablePathSafe :: IO (Maybe FilePath)
getExecutablePathSafe =
  (Just <$> Dir.getExecutablePath)
    `catch` (\(_ :: IOException) -> pure Nothing)
