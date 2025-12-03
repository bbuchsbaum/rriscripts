{-# LANGUAGE RecordWildCards #-}

-- A Haskell reimplementation of qexec.sh for submitting jobs to SLURM.
-- It keeps the original ergonomics (interactive vs batch, mem controls, logging)
-- while avoiding shell eval quirks and providing clearer error handling.

module Main (main) where

import Data.Char (isDigit)
import Data.List (find, intercalate)
import Data.Maybe (fromMaybe, isJust)
import System.Console.GetOpt
    ( ArgDescr(..)
    , ArgOrder(..)
    , OptDescr(..)
    , getOpt
    )
import System.Directory
    ( createDirectoryIfMissing
    , getPermissions
    , setPermissions
    , executable
    )
import System.Environment (getArgs, getProgName, lookupEnv)
import System.Exit (exitFailure, ExitCode(..))
import System.FilePath ((</>))
import System.IO (hClose, hPutStrLn, stderr)
import System.IO.Temp (withSystemTempFile)
import System.Process (readProcessWithExitCode)
import Text.Read (readMaybe)

data Options = Options
    { optTime        :: String
    , optInteractive :: Bool
    , optMem         :: Maybe String
    , optDisableMem  :: Bool
    , optNcpus       :: Int
    , optNodes       :: Int
    , optJobName     :: Maybe String
    , optArray       :: Maybe String
    , optArrayCmdFile:: Maybe FilePath
    , optAccount     :: String
    , optNoX11       :: Bool
    , optOmpThreads  :: Int
    , optLogDir      :: Maybe FilePath
    , optDryRun      :: Bool
    , optCommand     :: [String]
    } deriving (Show)

data EnvDefaults = EnvDefaults
    { envDefaultMem   :: Maybe String
    , envDisableMem   :: Bool
    , envDefaultLogDir :: Maybe FilePath
    }

data ParseResult = ParseHelp String | ParseError String

main :: IO ()
main = do
    envDefaults <- loadEnvDefaults
    args <- getArgs
    prog <- getProgName
    case parseOptions prog envDefaults args of
        Left (ParseHelp msg) -> putStrLn msg
        Left (ParseError err) -> hPutStrLn stderr err >> exitFailure
        Right opts -> run opts

loadEnvDefaults :: IO EnvDefaults
loadEnvDefaults = do
    envDefaultMem <- lookupEnv "QEXEC_DEFAULT_MEM"
    envDisableMem <- isJust <$> lookupEnv "QEXEC_DISABLE_MEM"
    envDefaultLogDir <- lookupEnv "QEXEC_LOG_DIR"
    pure EnvDefaults{..}

run :: Options -> IO ()
run opts@Options{..}
    | null optCommand && not optInteractive = failWith "A command is required unless interactive mode is used."
    | otherwise = do
        let memFlag = buildMemFlag opts
            timeFlag = "--time=" ++ renderTime optTime
            accountFlag = "--account=" ++ optAccount
            commonFlags =
                [ timeFlag
                , accountFlag
                , "--cpus-per-task=" ++ show optNcpus
                , "--nodes=" ++ show optNodes
                ]
                ++ maybe [] (\a -> ["--array=" ++ a]) optArray
                ++ maybe [] (:[]) memFlag
                ++ maybe [] (\n -> ["--job-name=" ++ n]) optJobName

        if optInteractive
            then runInteractive opts commonFlags
            else runBatch opts commonFlags

failWith :: String -> IO a
failWith msg = hPutStrLn stderr msg >> exitFailure

runInteractive :: Options -> [String] -> IO ()
runInteractive opts@Options{..} commonFlags = do
    let x11Flag = if optNoX11 then [] else ["--x11"]
        cmd = "salloc"
        fullArgs = commonFlags ++ x11Flag
    if optDryRun
        then dryRunSummary "salloc" fullArgs optCommand (buildMemFlag opts) optDisableMem
        else do
            (code, out, err) <- readProcessWithExitCode cmd fullArgs ""
            mapM_ (hPutStrLn stderr) (nonEmpty err)
            case code of
                ExitSuccess -> do
                    case parseAllocId out of
                        Just aid -> do
                            putStrLn $ "Allocated interactive session " ++ aid
                            putStrLn $ "ALLOCATION_ID=" ++ aid
                        Nothing  -> putStr   (out ++ if null out || last out == '\n' then "" else "\n")
                ExitFailure _ -> do
                    putStr   out
                    failWith ("salloc failed with exit code " ++ show code)

runBatch :: Options -> [String] -> IO ()
runBatch opts@Options{..} commonFlags =
    withSystemTempFile "qexec-job.sh" $ \path h -> do
        let commandLine = renderCommand (map expandTilde optCommand)
            scriptLines =
                [ "#!/bin/bash"
                , "set -euo pipefail"
                , "export OMP_NUM_THREADS=" ++ show optOmpThreads
                , "export MKL_NUM_THREADS=" ++ show optOmpThreads
                ]
                ++ arraySection optArrayCmdFile
                ++ [finalExec optArrayCmdFile commandLine]
        mapM_ (hPutStrLn h) scriptLines
        hClose h
        makeExecutable path

        let baseArgs = commonFlags
            logArgs = case optLogDir of
                Nothing -> []
                Just dir -> ["--output=" ++ dir </> "slurm-%j.out", "--error=" ++ dir </> "slurm-%j.err"]
            sbatchArgs = baseArgs ++ logArgs ++ [path]

    if optDryRun
        then dryRunSummary "sbatch" sbatchArgs optCommand (buildMemFlag opts) optDisableMem
        else do
            maybe (pure ()) ensureLogDir optLogDir
            (code, out, err) <- readProcessWithExitCode "sbatch" sbatchArgs ""
            mapM_ (hPutStrLn stderr) (nonEmpty err)
            case code of
                ExitSuccess -> do
                    case parseJobId out of
                        Just jid -> do
                            putStrLn $ "Submitted batch job " ++ jid
                            putStrLn $ "JOBID=" ++ jid
                        Nothing  -> putStr   (out ++ if null out || last out == '\n' then "" else "\n")
                ExitFailure _ -> do
                    putStr   out
                    failWith ("sbatch failed with exit code " ++ show code)

buildMemFlag :: Options -> Maybe String
buildMemFlag Options{..}
    | optDisableMem = Nothing
    | otherwise     = ("--mem=" ++) <$> optMem

renderCommand :: [String] -> String
renderCommand = intercalate " " . map shellQuote

shellQuote :: String -> String
shellQuote s = "'" ++ concatMap escape s ++ "'"
  where
    escape '\'' = "'\\''"
    escape c    = [c]

expandTilde :: String -> String
expandTilde ('~':'/':rest) = "$HOME/" ++ rest
expandTilde s              = s

renderTime :: String -> String
renderTime raw =
    case readMaybe raw :: Maybe Int of
        Just hours -> show (hours * 60) -- preserve original "hours" semantics
        Nothing    -> raw               -- allow direct Slurm time strings like 1:30:00

ensureLogDir :: FilePath -> IO ()
ensureLogDir dir = createDirectoryIfMissing True dir

arraySection :: Maybe FilePath -> [String]
arraySection Nothing = []
arraySection (Just fp) =
    [ "TASK_ID=${SLURM_ARRAY_TASK_ID:-0}"
    , "CMD_FILE=" ++ shellQuote (expandTilde fp)
    , "CMD=$(sed -n \"$((TASK_ID+1))p\" \"$CMD_FILE\")"
    , "if [ -z \"$CMD\" ]; then"
    , "  echo \"No command for TASK_ID=$TASK_ID in $CMD_FILE\" >&2"
    , "  exit 1"
    , "fi"
    ]

finalExec :: Maybe FilePath -> String -> String
finalExec Nothing commandLine = "exec " ++ commandLine
finalExec (Just _) _ = "exec bash -lc \"$CMD\""

makeExecutable :: FilePath -> IO ()
makeExecutable path = do
    perms <- getPermissions path
    setPermissions path perms { executable = True }

parseJobId :: String -> Maybe String
parseJobId txt = find (all isDigit) (words txt)

parseAllocId :: String -> Maybe String
parseAllocId txt = find (all isDigit) (words txt)

nonEmpty :: String -> [String]
nonEmpty s
    | null s    = []
    | otherwise = [s]

dryRunSummary :: String -> [String] -> [String] -> Maybe String -> Bool -> IO ()
dryRunSummary launcher args cmd memFlag disableMem = do
    putStrLn "Dry-run: Parsed arguments:"
    putStrLn $ "  Launcher: " ++ launcher
    putStrLn $ "  Args:     " ++ intercalate " " args
    putStrLn $ "  Command:  " ++ if null cmd then "<none>" else intercalate " " cmd
    putStrLn $ "  MEM:      " ++ fromMaybe "<none>" (fmap (drop (length "--mem=")) memFlag)
    putStrLn $ "  DISABLE_MEM: " ++ show disableMem

parseOptions :: String -> EnvDefaults -> [String] -> Either ParseResult Options
parseOptions prog EnvDefaults{..} argv =
    case getOpt Permute options argv of
        (flags, rest, [])
            | Help `elem` flags -> Left (ParseHelp (usageMessage prog))
            | otherwise         -> applyFlags base rest flags
        (_, _, errs)      -> Left (ParseError (concat errs ++ usageMessage prog))
  where
    base = Options
        { optTime = "1"
        , optInteractive = False
        , optMem = envDefaultMem
        , optDisableMem = envDisableMem
        , optNcpus = 1
        , optNodes = 1
        , optJobName = Nothing
        , optArray = Nothing
        , optArrayCmdFile = Nothing
        , optAccount = "rrg-brad"
        , optNoX11 = False
        , optOmpThreads = 1
        , optLogDir = envDefaultLogDir
        , optDryRun = False
        , optCommand = []
        }
    options =
        [ Option ['t'] ["time"] (ReqArg Time "HOURS") "Time in hours (numeric) or Slurm time string."
        , Option ['i'] ["interactive"] (NoArg Interactive) "Interactive job (salloc)."
        , Option ['m'] ["mem"] (ReqArg Mem "MEM") "Memory per node (opt-in; default unset)."
        , Option [] ["no-mem"] (NoArg NoMem) "Do not pass --mem to Slurm."
        , Option ['n'] ["ncpus"] (ReqArg Ncpus "N") "CPUs per task."
        , Option [] ["nodes"] (ReqArg Nodes "N") "Number of nodes."
        , Option ['j'] ["name"] (ReqArg JobName "NAME") "Job name."
        , Option ['a'] ["array"] (ReqArg Array "SPEC") "Array indices (e.g. 1-5 or 1-10%2)."
        , Option [] ["array-cmd-file"] (ReqArg ArrayCmdFile "FILE") "File with one command per array task index (0-based)."
        , Option [] ["account"] (ReqArg Account "ACCT") "Account name."
        , Option [] ["nox11"] (NoArg NoX11) "Disable X11 forwarding (interactive mode)."
        , Option ['o'] ["omp_num_threads"] (ReqArg Omp "N") "OMP/MKL threads."
        , Option ['l'] ["log-dir"] (ReqArg LogDir "DIR") "Directory for log output."
        , Option ['d'] ["dry-run"] (NoArg DryRun) "Show computed Slurm command and exit."
        , Option ['h'] ["help"] (NoArg Help) "Show help."
        ]

data Flag
    = Time String
    | Interactive
    | Mem String
    | NoMem
    | Ncpus String
    | Nodes String
    | JobName String
    | Array String
    | ArrayCmdFile FilePath
    | Account String
    | NoX11
    | Omp String
    | LogDir FilePath
    | DryRun
    | Help
    deriving (Eq, Show)

applyFlags :: Options -> [String] -> [Flag] -> Either ParseResult Options
applyFlags opts rest flags = foldl step (Right opts { optCommand = rest }) flags >>= validate
  where
    step acc flag = acc >>= \o -> case flag of
        Time t        -> Right o { optTime = t }
        Interactive   -> Right o { optInteractive = True }
        Mem m         -> Right o { optMem = Just m }
        NoMem         -> Right o { optDisableMem = True }
        Ncpus n       -> setInt "ncpus" (\v -> o { optNcpus = v }) n
        Nodes n       -> setInt "nodes" (\v -> o { optNodes = v }) n
        JobName n     -> Right o { optJobName = Just n }
        Array a       -> Right o { optArray = Just a }
        ArrayCmdFile f -> Right o { optArrayCmdFile = Just f }
        Account a     -> Right o { optAccount = a }
        NoX11         -> Right o { optNoX11 = True }
        Omp n         -> setInt "omp_num_threads" (\v -> o { optOmpThreads = v }) n
        LogDir d      -> Right o { optLogDir = Just d }
        DryRun        -> Right o { optDryRun = True }
        Help          -> Left (ParseHelp (usageMessage progName))

    progName = "qexec"

    setInt label setter raw =
        case readMaybe raw of
            Nothing -> Left $ ParseError $ "Invalid integer for --" ++ label ++ ": " ++ raw
            Just v  -> Right (setter v)

validate :: Options -> Either ParseResult Options
validate opts@Options{..}
    | Just a <- optArray
    , not (validArray a) = Left $ ParseError "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)."
    | isJust optArrayCmdFile && optArray == Nothing =
        Left $ ParseError "Error: --array-cmd-file requires --array to be set."
    | otherwise = Right opts

validArray :: String -> Bool
validArray = all (`elem` ("0123456789-%," :: String))

usageMessage :: String -> String
usageMessage prog =
    unlines
        [ "Usage: " ++ prog ++ " [options] <command>"
        , ""
        , "Options:"
        , "  -t, --time HOURS          Time in hours (numeric) or Slurm time string (default: 1)."
        , "  -i, --interactive         Submit an interactive job (salloc)."
        , "  -m, --mem MEM             Memory per node (default: not set)."
        , "      --no-mem              Do not pass --mem to Slurm (overrides -m/--mem or env default)."
        , "  -n, --ncpus N             Number of CPUs per task (default: 1)."
        , "      --nodes N             Number of nodes (default: 1)."
        , "  -j, --name NAME           Job name."
        , "  -a, --array SPEC          Array indices (e.g., 1-5 or 1-10%2)."
        , "      --account ACCT        Account name (default: rrg-brad)."
        , "      --nox11               Disable X11 forwarding (interactive mode)."
        , "  -o, --omp_num_threads N   Number of OpenMP/MKL threads (default: 1)."
        , "  -l, --log-dir DIR         Directory for log output (default: current dir or QEXEC_LOG_DIR)."
        , "  -d, --dry-run             Show computed SLURM command and exit."
        , "  -h, --help                Show this help message."
        , ""
        , "Environment:"
        , "  QEXEC_DISABLE_MEM=1       Skip --mem even if provided (for whole-node clusters)."
        , "  QEXEC_DEFAULT_MEM=VAL     Default memory request unless disabled or overridden."
        , "  QEXEC_LOG_DIR=DIR         Default directory for log output."
        ]
